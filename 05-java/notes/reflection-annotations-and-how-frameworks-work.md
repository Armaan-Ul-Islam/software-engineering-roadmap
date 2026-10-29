# Reflection, annotations and annotation processing: how Spring, Jackson and Lombok work

> **In one sentence:** An annotation is metadata with no behaviour of its own; something has to read it, and the two readers are reflection at run time (`Class`, `Method`, `Field`, `Proxy`, which is how Spring and Jackson work) and an annotation processor inside `javac` (which is how Lombok, MapStruct and the Spring Boot configuration metadata are generated).

**Why it matters:** Once you know that `@Transactional` is read by a `Proxy` wrapper and `@JsonProperty` by `getDeclaredMethods()`, an entire class of "the annotation does nothing" bugs becomes obvious: a method called through `this` rather than the proxy, a `private` field with no getter, an annotation whose retention is not `RUNTIME`, a constructor parameter name that is not in the class file. It is also why these frameworks have start-up cost, why GraalVM native image needs reachability metadata, and why `--add-opens` keeps appearing in your JVM arguments.

## The idea

**Annotations** are interfaces declared with `@interface`. `@Retention` decides how long they survive: `SOURCE` (discarded by `javac`, visible only to annotation processors, like `@Override` and Lombok's annotations), `CLASS` (in the class file, invisible to reflection, the default and almost never what you want), or `RUNTIME` (readable through reflection, which every Spring and Jackson annotation uses). `@Target` restricts where they may appear.

**Reflection** (`java.lang.reflect`) lets code inspect and use types it did not know at compile time. `Class.forName(name)` loads a class by its string name; `getDeclaredConstructors()`, `getDeclaredMethods()` and `getDeclaredFields()` list members including private ones; `isAnnotationPresent` and `getAnnotation` read `RUNTIME` annotations; `newInstance`, `invoke` and `get`/`set` use them. `setAccessible(true)` switches off the access check for private members, as long as the member's module allows it: your own code and any classpath library are in the unnamed module, which is fully open, but JDK packages are not, hence the `--add-opens java.base/java.lang=ALL-UNNAMED` flag whenever a library pokes into `String` or `ClassLoader` internals (see item 3.7).

**Dynamic proxies.** `Proxy.newProxyInstance(classLoader, interfaces, handler)` generates a class at run time that implements the given interfaces and routes every call to one `InvocationHandler`. That is the mechanism behind Spring's `@Transactional`, `@Cacheable`, `@Async` and Spring Data repositories (an interface with no implementation at all). When the bean has no interface, Spring uses CGLIB (bundled as `org.springframework.cglib`) to generate a subclass instead, which is why `final` classes and methods cannot be advised and why `this.otherMethod()` bypasses the advice: the proxy is a different object from the target.

**How Spring uses it.** Component scanning reads class files with ASM to find `@Component` without loading the classes, then instantiates the chosen ones by reflection, picking the constructor, resolving each parameter by type (and by name for ambiguity, which requires the `-parameters` compiler flag; Spring Framework 6.1 removed the fallback that read debug information), and calling `@PostConstruct` methods through `Method.invoke`. `@Value`, `@Autowired` on fields, `@Scheduled`, `@EventListener` and `@RequestMapping` are all found the same way.

**How Jackson uses it.** `ObjectMapper` introspects a class once, builds a serialiser from its getters, fields and annotations, caches it per type, and then calls the accessors by reflection for every object. Records are read through the canonical constructor's parameters, whose names are always in the class file (the `Record` attribute), which is why records need no `-parameters` flag while ordinary constructors with `@JsonCreator` do.

**Annotation processing** runs inside `javac`. A processor is a class implementing `javax.annotation.processing.Processor` (usually by extending `AbstractProcessor`), registered through `META-INF/services/javax.annotation.processing.Processor` or `-processor`. For each round, `javac` hands it the elements carrying the annotations it declared in `@SupportedAnnotationTypes`, and the processor may read them (through the `javax.lang.model` API, not reflection: the classes do not exist yet) and generate new source files, which `javac` then compiles in the next round. Standard processors cannot modify existing sources. MapStruct, Dagger, Immutables, the Spring Boot configuration-metadata processor and Micronaut all work this way. Lombok is the exception: it uses the processor hook to get into `javac` and edits the compiler's abstract syntax tree directly, which is why it needs the IDE plugin and occasionally breaks on new JDK releases (see item 9.4).

## Example: a hand-made `@Transactional`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Component {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Transactional {}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceOnly {}

interface OrderService {
    String place(String sku, int quantity);
}

@Component
@SourceOnly
class OrderServiceImpl implements OrderService {

    private final Map<String, Integer> stock;

    OrderServiceImpl(Map<String, Integer> stock) {
        this.stock = stock;
    }

    @Override
    @Transactional
    public String place(String sku, int quantity) {
        stock.merge(sku, -quantity, Integer::sum);
        return "placed " + quantity + " x " + sku;
    }
}

public class Reflect {

    public static void main(String[] arguments) throws ReflectiveOperationException {
        Class<?> type = Class.forName("OrderServiceImpl");
        System.out.println("@Component present : " + type.isAnnotationPresent(Component.class));
        System.out.println("@SourceOnly present : " + type.isAnnotationPresent(SourceOnly.class));

        Constructor<?> constructor = type.getDeclaredConstructors()[0];
        for (Parameter parameter : constructor.getParameters()) {
            System.out.println("constructor parameter : " + parameter.getType().getSimpleName() + " " + parameter.getName());
        }
        Map<String, Integer> stock = new HashMap<>(Map.of("sku-1", 10));
        Object target = constructor.newInstance(stock);

        Field stockField = type.getDeclaredField("stock");
        stockField.setAccessible(true);
        System.out.println("private final field read : " + stockField.get(target));

        Method place = type.getMethod("place", String.class, int.class);
        System.out.println("@Transactional on impl method : " + place.isAnnotationPresent(Transactional.class));
        System.out.println("@Transactional on interface method : "
            + OrderService.class.getMethod("place", String.class, int.class).isAnnotationPresent(Transactional.class));

        InvocationHandler handler = (proxy, method, methodArguments) -> {
            boolean transactional = target.getClass()
                .getMethod(method.getName(), method.getParameterTypes())
                .isAnnotationPresent(Transactional.class);
            if (transactional) {
                System.out.println("BEGIN");
            }
            try {
                Object result = method.invoke(target, methodArguments);
                if (transactional) {
                    System.out.println("COMMIT");
                }
                return result;
            } catch (InvocationTargetException exception) {
                if (transactional) {
                    System.out.println("ROLLBACK because " + exception.getCause());
                }
                throw exception.getCause();
            }
        };
        OrderService proxied = (OrderService) Proxy.newProxyInstance(
            OrderService.class.getClassLoader(), new Class<?>[] {OrderService.class}, handler);
        System.out.println(proxied.place("sku-1", 3));
        System.out.println("proxy class : " + proxied.getClass().getName());
        System.out.println("stock after : " + stock);
    }
}
```

`java Reflect.java` prints:

```text
@Component present : true
@SourceOnly present : false
constructor parameter : Map arg0
private final field read : {sku-1=10}
@Transactional on impl method : true
@Transactional on interface method : false
BEGIN
COMMIT
placed 3 x sku-1
proxy class : $Proxy3
stock after : {sku-1=7}
```

Three details to notice. `@SourceOnly` is invisible because of its retention. The constructor parameter is `arg0` because the file was compiled without `-parameters`; `javac -parameters` makes it `stock`, which is what Spring needs when two parameters share a type. And the annotation on the implementation method is not visible on the interface method: Spring's documentation says to annotate the class, not the interface, for the same reason.

Catching `InvocationTargetException` and rethrowing its cause is what every framework does; forgetting it is why a reflective call sometimes reports the wrong exception type.

## Example: a minimal annotation processor

A processor that generates a registry of every `@Component` class, in two files compiled first:

```java
import java.io.IOException;
import java.io.Writer;
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("Component")
@SupportedSourceVersion(SourceVersion.RELEASE_21)
public class ComponentRegistryProcessor extends AbstractProcessor {

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment roundEnvironment) {
        List<String> componentNames = roundEnvironment.getElementsAnnotatedWith(Component.class).stream()
            .map(Element::toString)
            .sorted()
            .toList();
        if (componentNames.isEmpty()) {
            return false;
        }
        processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, "components: " + componentNames);
        try (Writer writer = processingEnv.getFiler().createSourceFile("ComponentRegistry").openWriter()) {
            writer.write("import java.util.List;\n\npublic final class ComponentRegistry {\n");
            writer.write("    public static final List<String> NAMES = List.of(");
            writer.write(String.join(", ", componentNames.stream().map(name -> "\"" + name + "\"").toList()));
            writer.write(");\n}\n");
        } catch (IOException exception) {
            processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, exception.getMessage());
        }
        return true;
    }
}
```

Compiling an application with two `@Component` classes and a `main` that prints `ComponentRegistry.NAMES`:

```bash
javac -d out Component.java ComponentRegistryProcessor.java
javac -cp out -processor ComponentRegistryProcessor -s gen -d out App.java
java -cp out App
```

```text
Note: components: [InvoiceService, OrderService]
[InvoiceService, OrderService]
```

The generated `gen/ComponentRegistry.java` is ordinary source you can read and debug, which is the main argument for code generation over reflection: nothing happens at run time, and native image needs no metadata.

## Pitfalls

- Default retention. A custom annotation without `@Retention(RUNTIME)` is silently ignored by every reflective reader. It compiles, it appears in the source, it does nothing.
- Self-invocation. Advice lives in the proxy; `this.method()` never reaches it. Covered in the Spring domain, but the root cause is here: the proxy is a different object.
- Annotations on interfaces or private methods. JDK proxies see the interface, CGLIB subclasses see the class; private methods are not overridable, so no subclass can intercept them.
- Missing `-parameters`. Constructor parameter names fall back to `arg0`; Spring then cannot disambiguate two `String` parameters, and Jackson cannot bind a `@JsonCreator` constructor without `@JsonProperty` on each parameter. Spring Boot's parent POM sets the flag; a plain Maven project must add it to `maven-compiler-plugin`.
- `setAccessible` on JDK classes. `InaccessibleObjectException: module java.base does not "opens java.lang" to unnamed module` means a library is reaching into the JDK; fix the library version first and only then add `--add-opens`.
- Cost. `Method.invoke` and `Field.get` are much slower than a direct call on the first invocations and involve boxing; cache `Method` objects, or use `MethodHandle`s, and never look up members per request. Frameworks do all introspection at start-up for this reason.
- Native image. GraalVM cannot see what reflection will touch; anything not in the reachability metadata throws at run time. Prefer generated code or Spring's AOT processing when targeting it (see item 4.6).

## Check yourself

1. You write `@Retention(RetentionPolicy.CLASS) @interface Audited` and a Spring `BeanPostProcessor` that checks `isAnnotationPresent(Audited.class)`. What does it find, and why?
2. Why can a JDK dynamic proxy implement a Spring Data repository interface that has no implementing class, and what limits a proxy created this way?
3. Explain in one sentence each how Lombok differs from MapStruct in what it does during compilation, and why only one of them needs an IDE plugin.
4. A reflective call wraps the real exception in `InvocationTargetException`. Where in a framework stack trace would you expect to see this, and what should the framework do with it?

## Go deeper

- [Baeldung: Guide to Java Reflection](https://www.baeldung.com/java-reflection) · the API tour with runnable snippets.
- [Baeldung: Java Annotation Processing](https://www.baeldung.com/java-annotation-processing-builder) · a complete processor that generates a builder, including the service registration.
- [Spring Framework: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) · JDK versus CGLIB proxies and the self-invocation limitation, from the source.
- [java.lang.reflect.Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html) · the API documentation, including how `equals`, `hashCode` and `toString` are routed to the handler.
- [javax.lang.model package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/package-summary.html) · the model a processor sees instead of `Class` objects.

---

Part of [Java](../README.md) · item 3.4
