# Docker Compose for a local stack: app, PostgreSQL, Redis and Kafka

> **In one sentence:** Compose declares a set of containers, networks and volumes in one file, gives every service a DNS name on a private network, and with health-check-gated `depends_on` starts the whole stack in a working order with a single command.

**Why it matters:** Until the local stack is declared, every developer's machine is a different environment and onboarding is a wiki page of install steps. With a `compose.yaml` in the repository, `docker compose up` gives everyone the same PostgreSQL, Redis and Kafka, and the integration bugs that used to appear in staging (wrong host names, ports, start-up order) appear on the laptop instead.

## The idea

**Services, networks, volumes.** Each entry under `services` becomes a container from an `image` or a `build`. Compose creates one private bridge network per project (the project name defaults to the directory name) and attaches every service to it. Named entries under `volumes` persist data across restarts and are only deleted by `docker compose down -v`.

**Service DNS.** Inside the network, each service is reachable by its service name through Docker's embedded DNS: the app connects to `postgres:5432`, not to an IP and not to `localhost`. `localhost` inside a container is that container alone. `ports: "5432:5432"` publishes a container port on the *host*, which is for your IDE and `psql`, not for other containers.

**Environment and secrets.** `environment` sets variables; `${VAR:-default}` is interpolated from your shell or a `.env` file. Spring Boot's relaxed binding maps `SPRING_DATASOURCE_URL` to `spring.datasource.url`. For passwords, the top-level `secrets` block mounts a file at `/run/secrets/<name>` instead of putting the value in the environment where `docker inspect` and every child process can see it. The official PostgreSQL image reads `POSTGRES_PASSWORD_FILE`; Spring Boot reads a directory of secret files with `spring.config.import=optional:configtree:/run/secrets/`, which turns the file `db_password` into the property `db_password`.

**Start-up order.** A bare `depends_on` only orders container *start*, and PostgreSQL accepts connections a few seconds after its process starts. `condition: service_healthy` waits for the dependency's `healthcheck` to pass, so the app's connection pool and Flyway find a database that is actually ready. The other conditions are `service_started` and `service_completed_successfully` (for one-shot migration or seeding containers).

**Kafka in KRaft mode** runs without ZooKeeper: one container acts as broker and controller. It needs two listeners because a client connects to the bootstrap address and is then told the *advertised* address: containers must be told `kafka:9092` and host-side tools `localhost:29092`.

## Example: the complete `compose.yaml`

```yaml
services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: local
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/orders
      SPRING_DATASOURCE_USERNAME: orders
      SPRING_CONFIG_IMPORT: optional:configtree:/run/secrets/
      SPRING_DATA_REDIS_HOST: redis
      SPRING_KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      JAVA_TOOL_OPTIONS: -XX:MaxRAMPercentage=75.0
    secrets:
      - db_password
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 1g

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: orders
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orders -d orders"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  kafka:
    image: apache/kafka:4.0.0
    ports:
      - "29092:29092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,PLAINTEXT_HOST://:29092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_LOG_DIRS: /var/lib/kafka/data
      CLUSTER_ID: 4L6g3nShT-eMCtK--X86sw
    volumes:
      - kafka-data:/var/lib/kafka/data
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 10s
      retries: 12
      start_period: 20s

volumes:
  postgres-data:
  redis-data:
  kafka-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

What to notice:

1. The app's `SPRING_DATASOURCE_URL` uses the service name `postgres`; the app's own `ports` entry is only for your browser.
2. The password lives in `secrets/db_password.txt` (listed in `.gitignore`), is mounted into both containers, and the app reads it through `configtree`. In `application.yaml`: `spring.datasource.password: ${db_password}`. Write the file without a trailing newline: `printf 'local-dev-password' > secrets/db_password.txt`.
3. Each dependency has a health check that uses a tool shipped in its own image (`pg_isready`, `redis-cli`, `kafka-topics.sh`), and `start_period` gives Kafka time to format its log directory before failures count.
4. Kafka's `PLAINTEXT` listener is advertised as `kafka:9092` for containers and `PLAINTEXT_HOST` as `localhost:29092` for tools on your machine. The replication factors are 1 because there is one broker. `CLUSTER_ID` is any base64 UUID (the one above is from the Apache example; `kafka-storage.sh random-uuid` generates a fresh one), and changing it on an existing volume prevents the broker from starting.
5. `deploy.resources.limits.memory` is honoured by Compose and gives the JVM a limit to size itself from (item 3.4).

Daily commands:

```bash
docker compose up -d --build        # build the app image; the app starts only after its dependencies are healthy
docker compose ps                   # STATUS shows "healthy" for the dependencies
docker compose logs -f app
docker compose exec postgres psql -U orders -d orders
docker compose down                 # stop and remove containers; volumes survive
docker compose down -v              # also delete the volumes: a clean database next time
```

Spring Boot 3.1+ can also start this file for you: with the `spring-boot-docker-compose` dependency, `./mvnw spring-boot:run` runs `docker compose up` and derives the data source, Redis and Kafka connection details from the running containers.

## Pitfalls

- `localhost` inside a container. `jdbc:postgresql://localhost:5432/orders` in the app's environment gives `Connection refused` even though `psql -h localhost` from your terminal works, because the published port is on the host, not in the app's network namespace.
- Port collisions. A PostgreSQL already running on your machine makes `up` fail with "port is already allocated". Change only the host side: `"15432:5432"`.
- Stale volumes. PostgreSQL's initialisation (user, database, password, `docker-entrypoint-initdb.d` scripts) runs only on an empty data directory. Changing the password or the init script and restarting changes nothing until `down -v`.
- `depends_on` without a condition, or `service_healthy` on a service that has no `healthcheck` (Compose refuses to start).
- Kafka with a single listener advertised as `localhost`. Containers connect to the bootstrap address, are told to go to `localhost:9092`, and talk to themselves.
- Secrets in `environment` or committed `.env` files. They appear in `docker inspect`, in shell history and in Git.
- Treating the local stack as production topology. One network, one broker and replication factor 1 are deliberate simplifications.

## Check yourself

1. The app logs `Connection to localhost:5432 refused` while `psql -h localhost -U orders` from your terminal succeeds. Explain both observations with namespaces and published ports.
2. Why does Kafka need `PLAINTEXT` and `PLAINTEXT_HOST`, and what exactly fails if `KAFKA_ADVERTISED_LISTENERS` names only `kafka:9092`?
3. You changed the content of `secrets/db_password.txt` and ran `docker compose up -d`. The app cannot authenticate. Why, and which command fixes it?
4. What does `condition: service_healthy` guarantee about PostgreSQL, and what does it not guarantee about the application's own readiness?

## Go deeper

- [Docker Compose](https://docs.docker.com/compose/) · the official guide, from the first file to profiles and multiple environments.
- [Compose file reference](https://docs.docker.com/reference/compose-file/) · every key used above, including `depends_on` conditions, `healthcheck` and `secrets`.
- [Spring Boot: Development-time Services](https://docs.spring.io/spring-boot/reference/features/dev-services.html) · how Spring Boot starts a Compose file and derives connection details from it.
- [apache/kafka on Docker Hub](https://hub.docker.com/r/apache/kafka) · the KRaft configuration variables and the official single-broker examples.

---

Part of [DevOps & Delivery](../README.md) · item 3.5
