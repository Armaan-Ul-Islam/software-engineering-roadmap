# Docker fundamentals for a Spring Boot service

> **In one sentence:** A container is an ordinary Linux process given its own view of the filesystem, network and process table, started from an image whose read-only layers are cached and shared, so a good Dockerfile orders its instructions from least to most frequently changed, splits the Spring Boot jar into layers, and runs the application as an unprivileged user.

**Why it matters:** The difference between a careless and a careful Dockerfile is a build that re-downloads every dependency on each commit versus one that rebuilds a 16 kB layer, an image that runs as root versus one a cluster policy will admit, and a build that is reproducible versus one that changes when a base tag moves. Interviewers ask "what is a container" to find out whether you think it is a small virtual machine.

## The idea

**A container is a process, not a machine.** The kernel gives the process a private view of the system through *namespaces* (pid: it sees only its own processes; net: its own interfaces and ports; mnt: its own root filesystem; plus uts, ipc and user) and limits what it may consume through *cgroups* (CPU time, memory, number of processes). There is no hypervisor and no second kernel: `uname -r` inside the container prints the host kernel, and a memory limit of 1 GiB is a cgroup setting that the kernel enforces by killing the process (item 3.4).

**An image is a stack of read-only layers plus metadata.** Each layer is a tarball of filesystem changes, addressed by the digest of its content. A union filesystem (overlay2 on most hosts) presents the stack as one directory tree. Starting a container adds a thin writable layer on top; `docker rm` throws it away. Images are immutable and shared, containers are disposable, and nothing written inside a running container survives unless it goes to a volume.

**Layers are the build cache.** `RUN`, `COPY` and `ADD` create layers; `ENV`, `WORKDIR`, `USER`, `EXPOSE` and `ENTRYPOINT` only change metadata. BuildKit reuses a layer when the instruction and all of its inputs (for `COPY`, the checksums of the copied files) are unchanged, and the first instruction that misses the cache invalidates every later one. So copy `pom.xml` and resolve dependencies *before* copying `src`.

**Multi-stage builds** keep the JDK, Maven and sources in a build stage and copy only the result into a small runtime stage with `COPY --from=`. The final image contains no compiler, no sources and no build cache.

**Layered jars.** A Spring Boot executable jar is a single file of 40 to 80 MB; copying it creates one layer, and every build pushes it whole. Spring Boot writes a `layers.idx` into the jar that splits it into `dependencies`, `spring-boot-loader`, `snapshot-dependencies` and `application`. Since Spring Boot 3.3 the `tools` jar mode extracts them: `java -Djarmode=tools -jar application.jar extract --layers --destination extracted`. The `application` directory then holds a slim `application.jar` whose manifest points at `lib/`, so the runtime stage starts it with a plain `java -jar`. Before 3.3 the equivalent was `java -Djarmode=layertools -jar application.jar extract`, started with `java org.springframework.boot.loader.launch.JarLauncher` (`org.springframework.boot.loader.JarLauncher` before 3.2); the `tools` mode reproduces that exploded layout if you add `--launcher`.

**Pin the base image.** `eclipse-temurin:21-jre` is a moving tag. Pin at least to a distribution tag such as `eclipse-temurin:21-jre-jammy`, and for a reproducible build pin the digest (`docker buildx imagetools inspect eclipse-temurin:21-jre-jammy` prints it as `@sha256:...`) and let Renovate or Dependabot propose the bumps (item 2.6).

**Run as a non-root user, and keep the context clean.** Root inside the container is root on the host kernel, one kernel bug or mounted socket away from the host; create a system user and switch to it with `USER`, because policies such as `runAsNonRoot: true` refuse images that do not. A `.dockerignore` keeps `target/`, `.git/` and secrets out of the build context, which otherwise is sent to the daemon in full on every build.

## Example: the Dockerfile, annotated

```dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:21-jdk-jammy AS build
WORKDIR /workspace
COPY mvnw pom.xml ./
COPY .mvn .mvn
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -ntp dependency:go-offline
COPY src src
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -ntp -DskipTests package \
    && cp target/*.jar application.jar \
    && java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:21-jre-jammy
RUN groupadd --system spring && useradd --system --gid spring --no-create-home spring
WORKDIR /application
COPY --from=build --chown=spring:spring /workspace/extracted/dependencies/ ./
COPY --from=build --chown=spring:spring /workspace/extracted/spring-boot-loader/ ./
COPY --from=build --chown=spring:spring /workspace/extracted/snapshot-dependencies/ ./
COPY --from=build --chown=spring:spring /workspace/extracted/application/ ./
USER spring
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
```

1. `# syntax=docker/dockerfile:1` selects the current Dockerfile frontend, which `--mount=type=cache` needs.
2. The build stage copies the Maven wrapper and `pom.xml` first and runs `dependency:go-offline`; that layer is reused for as long as the POM is unchanged.
3. `--mount=type=cache,target=/root/.m2` keeps the local Maven repository in a BuildKit cache outside any layer, so even a POM change downloads only what is new. On a fresh CI builder this cache starts empty (item 2.3).
4. `cp target/*.jar application.jar` gives the jar a stable name; `extract --layers --destination extracted` writes the four layer directories.
5. The runtime stage is a JRE image: smaller and with less to patch, at the price of having no `jcmd` or `jstack`. Keep the JDK variant for debugging.
6. `groupadd` and `useradd --system` create an unprivileged user, `--chown` makes the files readable by it, and `USER spring` switches before the entrypoint runs.
7. The four `COPY` lines run from least to most frequently changed.
8. `ENTRYPOINT` uses the exec form so the JVM is PID 1 and receives `SIGTERM` directly, which graceful shutdown depends on (item 4.6). JVM flags are not baked in; they go in `JAVA_TOOL_OPTIONS` at deploy time (item 3.4).

The matching `.dockerignore`:

```text
target/
.git/
.idea/
*.iml
.env
secrets/
```

Built against a fresh `start.spring.io` project (web, actuator, JPA, PostgreSQL, Redis, Kafka), the layers come out like this:

```text
$ docker image history orders:dev --format 'table {{.CreatedBy}}\t{{.Size}}' | head -8
CREATED BY                                      SIZE
ENTRYPOINT ["java" "-jar" "application.jar"]    0B
EXPOSE [8080/tcp]                               0B
USER spring                                     0B
COPY --chown=spring:spring /workspace/extrac…   16.4kB     <- application: the only layer a code change rebuilds
COPY --chown=spring:spring /workspace/extrac…   4.1kB      <- snapshot-dependencies
COPY --chown=spring:spring /workspace/extrac…   4.1kB      <- spring-boot-loader
COPY --chown=spring:spring /workspace/extrac…   86.4MB     <- dependencies: 101 jars, cached until the POM changes
$ docker run --rm --entrypoint id orders:dev
uid=999(spring) gid=999(spring) groups=999(spring)
```

**Buildpacks instead of a Dockerfile.** `./mvnw spring-boot:build-image` runs Cloud Native Buildpacks (the Paketo builder) and needs no Dockerfile: it produces a layered image with a non-root user, a JVM whose memory settings are calculated from the container limit at start-up, and reproducible timestamps. You give up control over the base OS, its packages and the exact flags (configuration happens through `BP_*` and `BPL_*` variables), you need a Docker daemon to build, and debugging an image means learning buildpack conventions. Teams that already own their images keep the Dockerfile; teams that want a secure, maintained default take the buildpack.

Two further options from item 3.3: `gcr.io/distroless/java21-debian12:nonroot` removes the shell and package manager (so `kubectl exec ... sh` no longer works; use ephemeral debug containers, item 4.8), and the Spring Boot documentation shows a class-data-sharing training run in the runtime stage, `java -XX:ArchiveClassesAtExit=application.jsa -Dspring.context.exit=onRefresh -jar application.jar`, after which the entrypoint adds `-XX:SharedArchiveFile=application.jsa` for faster start-up.

## Pitfalls

- `COPY . .` before resolving dependencies. Every source change invalidates the dependency layer and the build downloads Maven Central again; the hundredth build takes as long as the first.
- One `COPY target/*.jar app.jar`. The whole application is a single layer, so every push and pull moves the full jar when one class changed.
- Floating tags. `FROM eclipse-temurin:21-jre` or `:latest` produces different images on different days, and a build that passed yesterday fails today with no change in your repository.
- Running as root because the base image does. A `runAsNonRoot` policy rejects the Pod with `CreateContainerConfigError`, or worse, nobody notices.
- Secrets in `ARG`, `ENV` or a copied `settings.xml`. They stay in the image history for anyone with pull access. Use `RUN --mount=type=secret` for build-time credentials.

## Check yourself

1. Why does changing one Java class rebuild only the 16 kB layer in the example, and which two instructions would you have to swap to lose that property?
2. Containers share the host kernel. What does that imply for an x86_64 image on an ARM laptop, and for a kernel vulnerability on a node that runs fifty containers?
3. A colleague says `FROM eclipse-temurin:21-jre-jammy` is pinned. What still changes underneath it, and what would you add to make the build reproducible?
4. List everything from the build stage that ends up in the final image of the example. Then list what a buildpack-built image gives you that this Dockerfile does not.

## Go deeper

- [Docker: Building best practices](https://docs.docker.com/build/building/best-practices/) · the official list: multi-stage, cache ordering, non-root, pinned images.
- [Spring Boot: Efficient container images](https://docs.spring.io/spring-boot/reference/packaging/container-images/efficient-images.html) and [Spring Boot: Dockerfiles](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html) · the layered-jar mechanism and the reference Dockerfile this one is based on.
- [Julia Evans: What even is a container](https://jvns.ca/blog/2016/10/10/what-even-is-a-container/) · namespaces and cgroups explained from first principles.
- [Docker: Java language-specific guide](https://docs.docker.com/guides/java/) · an end-to-end walkthrough for a Spring application.
- [Docker: Build cache](https://docs.docker.com/build/cache/) · exactly when a layer is reused and when it is not.

---

Part of [DevOps & Delivery](../README.md) · items 3.1, 3.2, 3.3
