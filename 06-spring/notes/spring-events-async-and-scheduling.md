# Application events, @Async and @Scheduled

> **In one sentence:** `publishEvent` calls every matching `@EventListener` synchronously on the publishing thread, inside the publisher's transaction if there is one, so a listener that must only act on committed data needs `@TransactionalEventListener`, a listener that must not delay the caller needs `@Async` on an executor you sized yourself, and anything that must reach another service reliably needs an outbox rather than an in-process event.

**Why it matters:** Events are how a Spring application separates "place the order" from "send the confirmation" without a message broker, and the defaults are exactly wrong for that: the email goes out before the commit, the HTTP response waits for the mail server, and when the transaction rolls back the customer has already been thanked for an order that does not exist. Scheduling has its own trap: Boot's default scheduler has one thread, so one slow job silently delays every other job in the application.

## The idea

**Publishing and listening.** Inject `ApplicationEventPublisher` and call `publishEvent(Object)`; since Spring 4.2 any object is an event, so a record is the usual choice. A method annotated `@EventListener` on any bean receives every event assignable to its parameter type. The dispatch is done by `SimpleApplicationEventMulticaster`, which by default has no executor: it loops over the listeners and calls each one on the publishing thread, and `publishEvent` returns only when all of them have returned. Three consequences follow:

1. A listener runs inside the publisher's transaction, before the commit. It sees the uncommitted rows, and if it throws, the exception propagates out of `publishEvent` into the publisher and the transaction rolls back.
2. Anything the listener does outside the database (email, HTTP call, Kafka send) happens whether or not the transaction later commits.
3. The caller's latency includes every listener.

**`@TransactionalEventListener`** binds the listener to the transaction instead. The `phase` is `BEFORE_COMMIT`, `AFTER_COMMIT` (the default), `AFTER_ROLLBACK` or `AFTER_COMPLETION`. Under the hood `publishEvent` registers a `TransactionSynchronization` with `TransactionSynchronizationManager`, and the listener is invoked from its `afterCommit` callback, still on the publishing thread. Two traps live here:

- **No transaction, no event.** If `publishEvent` runs with no transaction active, the listener is never invoked, silently. `fallbackExecution = true` makes it run immediately in that case. A test that calls the service without a transaction is the usual way to discover this.
- **After commit is not a new transaction.** In the `AFTER_COMMIT` phase the transaction has committed but its resources are still bound to the thread. A plain `@Transactional` on the listener joins that finished transaction and its writes are never committed, with no error. The listener must declare `@Transactional(propagation = Propagation.REQUIRES_NEW)`, or run on another thread. An exception thrown in this phase cannot undo the commit; Spring propagates it to the caller of the transactional method, which then sees a failure for work that succeeded.

**`@Async`** moves a call to an executor and returns immediately; the return type must be `void`, `Future<T>` or `CompletableFuture<T>`. It needs `@EnableAsync` on a configuration class and it is a proxy, so self-invocation runs synchronously (item 1.4). The executor is chosen by name: the value in `@Async("eventExecutor")`, otherwise the single `TaskExecutor` bean, otherwise a bean named `taskExecutor`. Boot auto-configures `applicationTaskExecutor` from `spring.task.execution.*`: eight core threads and an unbounded queue, so `max-size` is never reached and a burst of work queues forever rather than growing the pool. Exceptions from a `void` `@Async` method never reach the caller; they go to an `AsyncUncaughtExceptionHandler`, which by default only logs. With a `CompletableFuture` return type the future completes exceptionally instead. The transaction and the `SecurityContext` are thread-bound and do not follow (item 4.3).

Combining `@Async` with `@TransactionalEventListener` is the standard recipe for "after the order is committed, do something slow": the event is dispatched after commit, on another thread, so the response is not delayed, and because the thread is new, a plain `@Transactional` on the listener starts a real transaction without `REQUIRES_NEW`.

**`@Scheduled`** needs `@EnableScheduling` and a method without parameters. `fixedDelay` waits the given time after each run ends, `fixedRate` starts runs at a fixed interval but never concurrently with itself, and `cron` takes a six-field expression with seconds first, plus macros such as `@hourly` and a `zone`. Durations can be ISO strings: `fixedDelayString = "PT5M"`. Boot provides a `ThreadPoolTaskScheduler` with `spring.task.scheduling.pool.size=1`. One thread for every job in the application: a report that takes four minutes delays the cleanup that should run every minute, and nothing warns you. An exception in a scheduled method is logged ("Unexpected error occurred in scheduled task") and the schedule continues. In a cluster every instance runs every job; use a database lock or a library such as ShedLock when a job must run exactly once.

**The outbox.** Spring events never leave the process, and nothing guarantees delivery: if the process dies between the commit and the `AFTER_COMMIT` listener, the event is gone. When another service must learn about the order, write the event to an `outbox` table in the same transaction as the order and let a relay publish it to the broker afterwards. Spring Modulith's event publication registry does exactly this for Spring events, persisting each publication and retrying it after a restart; Debezium does it by tailing the database log (item 9.3).

## Example: an order-placed event handled after commit

```java
public record OrderPlaced(Long orderId, String customerEmail) {
}
```

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(OrderRepository orderRepository, ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long place(PlaceOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));
        eventPublisher.publishEvent(new OrderPlaced(order.getId(), command.customerEmail()));
        return order.getId();
    }
}
```

```java
@Component
public class OrderPlacedListeners {

    private final ConfirmationMailer confirmationMailer;
    private final AuditLogRepository auditLogRepository;

    public OrderPlacedListeners(ConfirmationMailer confirmationMailer, AuditLogRepository auditLogRepository) {
        this.confirmationMailer = confirmationMailer;
        this.auditLogRepository = auditLogRepository;
    }

    @Async("eventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void sendConfirmation(OrderPlaced event) {
        confirmationMailer.sendOrderConfirmation(event.customerEmail(), event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAudit(OrderPlaced event) {
        auditLogRepository.save(AuditEntry.orderPlaced(event.orderId()));
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableScheduling
public class BackgroundWorkConfiguration {

    @Bean
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("event-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

On `place`: the order is inserted, `publishEvent` registers two synchronizations and returns at once, the transaction commits, `recordAudit` runs on the request thread in its own short transaction, `sendConfirmation` is handed to an `event-` thread, and the controller returns. If the insert fails, neither listener runs. The queue is bounded on purpose: once 500 tasks wait, `CallerRunsPolicy` makes the publishing thread send the email itself, slowing one request instead of growing the heap until the process dies. Note that defining any `Executor` bean makes Boot's `applicationTaskExecutor` back off; if Spring MVC's async support also needs one, define a second bean with that name.

To watch the phases, log the transaction interceptor and the event adapter:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.event=DEBUG
```

The line `No transaction is active - skipping OrderPlaced[...]` is the "no transaction, no event" trap caught in the act.

## Example: a scheduled job with a proper pool

```java
@Component
public class ExpiredReservationCleaner {

    private static final Logger log = LoggerFactory.getLogger(ExpiredReservationCleaner.class);

    private final ReservationRepository reservationRepository;
    private final Clock clock;

    public ExpiredReservationCleaner(ReservationRepository reservationRepository, Clock clock) {
        this.reservationRepository = reservationRepository;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "PT1M", initialDelayString = "PT30S")
    @Transactional
    public void releaseExpired() {
        int released = reservationRepository.releaseExpiredBefore(clock.instant());
        if (released > 0) {
            log.info("released {} expired reservations", released);
        }
    }
}
```

```properties
spring.task.scheduling.pool.size=4
spring.task.scheduling.thread-name-prefix=scheduling-
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=30s
```

`fixedDelay` rather than `fixedRate` so that a slow database cannot make runs pile up; the pool size so that this job and the nightly export do not share one thread; the shutdown settings so that a rolling deployment waits for a running job instead of killing it half-way. With `spring.threads.virtual.enabled=true` (item 3.7) Boot replaces executor and scheduler with virtual-thread variants and the pool sizes stop mattering.

## Pitfalls

- Sending email or calling another system from a plain `@EventListener` inside a transaction. The message leaves before the commit, and still leaves if the transaction rolls back.
- `@TransactionalEventListener` plus a default `@Transactional`. In the `AFTER_COMMIT` phase the listener joins a transaction that has already committed; its writes vanish without an exception. Use `REQUIRES_NEW` or `@Async`.
- Testing with `@Transactional` on the test class. The test transaction is rolled back at the end, so `AFTER_COMMIT` listeners never fire and the test passes or fails for the wrong reason. Call `TestTransaction.flagForCommit()` and `TestTransaction.end()`, or test without a test-managed transaction (item 7.6).
- `@Async` without `@EnableAsync`, or on a method called from the same class. Both run synchronously with no warning. Check the thread name in the log.
- One executor for everything, or the default scheduler for every job. A slow report fills the queue and the confirmations wait behind it; a long job on the single scheduler thread delays every other job. Give independent workloads their own bounded executors and raise `spring.task.scheduling.pool.size`.
- Treating in-process events as reliable messaging. A crash between commit and listener loses the event, and a `publishEvent` inside a `REQUIRES_NEW` transaction fires on that inner commit, not the outer one. For cross-service effects, use an outbox.

## Check yourself

1. An `AFTER_COMMIT` listener annotated with plain `@Transactional` writes an audit row. The table stays empty and nothing is thrown. Why, and which two changes fix it?
2. Your integration test is `@Transactional` and asserts that the confirmation was sent after `orderService.place`. It fails. Why, and what does `TestTransaction` let you do?
3. A plain `@Async @EventListener` loads the order by id and sometimes logs "order not found". Describe the race and the one-annotation fix.
4. With Boot's defaults, what happens when a nightly export takes twenty minutes while a per-minute cleanup job exists, and what happens when ten thousand events are published in one burst?

## Go deeper

- [Spring: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events) · `@EventListener`, ordering, asynchronous listeners and generic events.
- [Spring: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) · the phases, `fallbackExecution` and the warning about data access after commit.
- [Spring: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) · `@Async`, `@Scheduled`, cron syntax and the executor abstractions.
- [Spring Boot: Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html) · what Boot auto-configures and every `spring.task.*` property.
- [Spring Modulith: Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) · the event publication registry, which turns Spring events into a persisted outbox.
- [ShedLock](https://github.com/lukas-krecan/ShedLock) · the usual answer to "this `@Scheduled` job must run on one instance only".

---

Part of [Spring](../README.md) · items 1.6, 4.4
