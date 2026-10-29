# Architecture & Craft

> Writing code other people can change: readable code, SOLID without dogma, the patterns you actually use, refactoring safely, testing strategy, domain-driven design, hexagonal and modular architecture, API design, and the writing (design docs, ADRs, code review) that distinguishes a senior engineer.

**Prerequisites:** [Java](../05-java/README.md)

**Done when you can:**

- Take a 400-line class and split it into intention-revealing pieces without changing behaviour, with tests that prove it.
- Explain each SOLID principle with a concrete Java example of the problem it prevents, and say when it does not apply.
- Structure a Spring Boot service so the domain depends on neither the framework nor the database, and defend the cost of doing so.
- Write a testing strategy for a service: what gets unit tests, integration tests and contract tests, and why.
- Model a non-trivial domain with aggregates, value objects and domain events, and explain where the boundaries are.
- Write a one-page design document or ADR that a reviewer can approve or reject without a meeting.

## Roadmap

### 1. Readable code

- [ ] 1.1 Naming: intention-revealing names, full words, one vocabulary per concept; names as the first design tool · [notes](notes/naming-and-readable-code.md) · [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php) · [Kevlin Henney: Seven Ineffective Coding Habits of Many Programmers](https://www.youtube.com/watch?v=ZsHMHukIlJY)
- [ ] 1.2 Functions and classes: deep modules, one reason to change, cohesion and coupling, the cost of shallow abstractions · [notes](notes/naming-and-readable-code.md) · [John Ousterhout: A Philosophy of Software Design (talk)](https://www.youtube.com/watch?v=bmSAYlu0NcY)
- [ ] 1.3 Comments and documentation: why over what; when a comment is a smell; docs that live next to the code · [notes](notes/naming-and-readable-code.md) · [Google Java Style Guide: Javadoc](https://google.github.io/styleguide/javaguide.html#s7-javadoc)
- [ ] 1.4 Errors and nulls: fail fast, exceptions vs result types, `Optional`, parse-don't-validate, the billion-dollar mistake · [notes](notes/parse-dont-validate-and-value-objects.md) · [Alexis King: Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) · [Tony Hoare: Null References, The Billion Dollar Mistake](https://www.infoq.com/presentations/Null-References-The-Billion-Dollar-Mistake-Tony-Hoare/)
- [ ] 1.5 Immutability and value objects; making illegal states unrepresentable with types · [notes](notes/parse-dont-validate-and-value-objects.md) · [Fowler: Value Object](https://martinfowler.com/bliki/ValueObject.html)
- [ ] 1.6 Code smells: a shared vocabulary for code review · [notes](notes/code-smells-catalogue.md) · [refactoring.guru: Code Smells](https://refactoring.guru/refactoring/smells)

### 2. Design principles

- [ ] 2.1 SOLID: the problem each principle prevents, with Java examples, and the cases where it does not apply · [notes](notes/solid-in-practice.md) · [Baeldung: SOLID Principles](https://www.baeldung.com/solid-principles) · [Robert C. Martin: Solid Relevance](https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html)
- [ ] 2.2 DRY, KISS, YAGNI, and the duplication that is cheaper than the wrong abstraction · [notes](notes/coupling-cohesion-and-the-wrong-abstraction.md) · [Sandi Metz: The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)
- [ ] 2.3 Coupling and cohesion; connascence; dependency direction and dependency inversion in practice · [notes](notes/coupling-cohesion-and-the-wrong-abstraction.md) · [Connascence](https://connascence.io/)
- [ ] 2.4 Composition over inheritance; interfaces as roles; Law of Demeter; Tell, Don't Ask · [notes](notes/composition-over-inheritance-and-tell-dont-ask.md) · [Composition over inheritance](https://en.wikipedia.org/wiki/Composition_over_inheritance) · [Fowler: Tell, Don't Ask](https://martinfowler.com/bliki/TellDontAsk.html)
- [ ] 2.5 Information hiding and modularity (Parnas); deep vs shallow modules · [notes](notes/composition-over-inheritance-and-tell-dont-ask.md) · [Parnas: On the Criteria To Be Used in Decomposing Systems into Modules](https://www.win.tue.nl/~wstomv/edu/2ip30/references/criteria_for_modularization.pdf)

### 3. Design patterns that earn their keep

- [ ] 3.1 Creational: Builder, Factory Method, Abstract Factory; when plain `new` is fine · [notes](notes/design-patterns-you-actually-use.md) · [refactoring.guru: Design Patterns](https://refactoring.guru/design-patterns) · [Java Design Patterns](https://java-design-patterns.com/)
- [ ] 3.2 Structural: Adapter, Decorator, Facade, Proxy, Composite; where Spring uses each · [notes](notes/design-patterns-you-actually-use.md) · [refactoring.guru: Structural patterns](https://refactoring.guru/design-patterns/structural-patterns)
- [ ] 3.3 Behavioural: Strategy, Template Method, Observer, Command, Chain of Responsibility, State; replacing conditionals with polymorphism · [notes](notes/design-patterns-you-actually-use.md) · [refactoring.guru: Behavioral patterns](https://refactoring.guru/design-patterns/behavioral-patterns)
- [ ] 3.4 Enterprise patterns: Repository, Unit of Work, Service Layer, DTO, Specification; where Spring Data and JPA fit · [Fowler: Catalog of Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/)
- [ ] 3.5 Anti-patterns: god class, anemic domain model, service locator, singletons as globals, primitive obsession · [notes](notes/code-smells-catalogue.md) · [Fowler: Anemic Domain Model](https://martinfowler.com/bliki/AnemicDomainModel.html)
- [ ] 3.6 Functional patterns in Java: pure functions, higher-order functions, pipelines; sealed types with pattern matching instead of Visitor · [dev.java: Pattern Matching](https://dev.java/learn/language/fp/pattern-matching/)

### 4. Refactoring

- [ ] 4.1 The catalogue: extract and inline method/class, move, rename, replace conditional with polymorphism, introduce parameter object · [notes](notes/refactoring-safely.md) · [Refactoring (Fowler)](https://refactoring.com/) · [refactoring.guru: Refactoring](https://refactoring.guru/refactoring)
- [ ] 4.2 Working safely: characterisation tests, seams, small steps, IDE refactorings, one commit per step · [notes](notes/refactoring-safely.md) · [Working Effectively with Legacy Code](https://www.oreilly.com/library/view/working-effectively-with/0131177052/)
- [ ] 4.3 Refactoring at scale: strangler fig, branch by abstraction, parallel change, the Mikado method · [notes](notes/strangler-fig-and-refactoring-at-scale.md) · [Fowler: Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html) · [The Mikado Method](https://mikadomethod.info/)
- [ ] 4.4 Technical debt: naming it, making it visible, paying it down deliberately · [notes](notes/strangler-fig-and-refactoring-at-scale.md) · [Fowler: Technical Debt Quadrant](https://martinfowler.com/bliki/TechnicalDebtQuadrant.html)
- [ ] 4.5 Tidyings: the small, safe cleanups to make before and after a change · [Kent Beck: Tidy First?](https://www.oreilly.com/library/view/tidy-first/9781098151232/)

### 5. Testing strategy

- [ ] 5.1 Why we test: fast feedback, design pressure, regression safety; the test pyramid and the testing trophy · [notes](notes/testing-strategy.md) · [Ham Vocke: The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) · [Kent C. Dodds: The Testing Trophy](https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications)
- [ ] 5.2 Unit tests that survive refactoring: test behaviour not implementation, one reason to fail, naming, arrange-act-assert · [notes](notes/testing-strategy.md) · [Unit Testing Principles, Practices, and Patterns](https://www.manning.com/books/unit-testing)
- [ ] 5.3 Test doubles: dummies, stubs, fakes, mocks, spies; classicist vs mockist; when mocks hurt · [notes](notes/testing-strategy.md) · [Fowler: Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html) · [Fowler: Test Double](https://martinfowler.com/bliki/TestDouble.html)
- [ ] 5.4 Integration tests with real infrastructure (Testcontainers), consumer-driven contract tests (Pact), and few, valuable end-to-end tests · [notes](notes/contract-testing-with-pact.md) · [Testcontainers](https://testcontainers.com/) · [Pact](https://docs.pact.io/)
- [ ] 5.5 TDD as a design practice; outside-in development with acceptance tests · [notes](notes/tdd-as-a-design-practice.md) · [Growing Object-Oriented Software, Guided by Tests](http://www.growing-object-oriented-software.com/) · [Kent Beck: Canon TDD](https://tidyfirst.substack.com/p/canon-tdd)
- [ ] 5.6 Test quality: flaky tests, test data builders, property-based and mutation testing, coverage as a smell detector · [notes](notes/tdd-as-a-design-practice.md) · [Kent Beck: Test Desiderata](https://testdesiderata.com/) · [Fowler: Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html)

### 6. Domain-driven design

- [ ] 6.1 Strategic design: ubiquitous language, bounded contexts, context maps, core vs supporting vs generic subdomains · [notes](notes/domain-driven-design-essentials.md) · [Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html) · [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [ ] 6.2 Tactical design: entities, value objects, aggregates and invariants, repositories, domain services, domain events · [notes](notes/domain-driven-design-essentials.md) · [Vaughn Vernon: Effective Aggregate Design](https://www.dddcommunity.org/library/vernon_2011/)
- [ ] 6.3 Aggregates and transactions: one aggregate per transaction, eventual consistency between aggregates, keeping aggregates small · [notes](notes/domain-driven-design-essentials.md) · [Vaughn Vernon: Effective Aggregate Design](https://www.dddcommunity.org/library/vernon_2011/)
- [ ] 6.4 Anti-corruption layers and integrating with legacy or external systems · [Azure Architecture Center: Anti-corruption Layer pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer)
- [ ] 6.5 Domain discovery: event storming and domain storytelling · [EventStorming](https://www.eventstorming.com/) · [Domain Storytelling](https://domainstorytelling.org/)
- [ ] 6.6 DDD in Java and Spring: domain model vs JPA entities, where annotations go, mapping at the edges, Spring Modulith · [Herberto Graça: DDD, Hexagonal, Onion, Clean, CQRS... how I put it all together](https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/) · [Spring Modulith](https://docs.spring.io/spring-modulith/reference/)

### 7. Application architecture

- [ ] 7.1 Layered architecture, its failure modes, and the dependency rule · [notes](notes/hexagonal-architecture-with-spring-boot.md) · [Fowler: Presentation Domain Data Layering](https://martinfowler.com/bliki/PresentationDomainDataLayering.html)
- [ ] 7.2 Hexagonal (ports and adapters), onion and clean architecture: the shared idea and the differences · [notes](notes/hexagonal-architecture-with-spring-boot.md) · [Alistair Cockburn: Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) · [Robert C. Martin: The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [ ] 7.3 Modular monolith: package by feature, enforcing boundaries (ArchUnit, Spring Modulith, JPMS), extracting services later · [notes](notes/modular-monolith.md) · [ArchUnit](https://www.archunit.org/) · [Spring Modulith](https://docs.spring.io/spring-modulith/reference/)
- [ ] 7.4 Vertical slices and use-case-centred organisation · [Jimmy Bogard: Vertical Slice Architecture](https://www.jimmybogard.com/vertical-slice-architecture/)
- [ ] 7.5 Architecture characteristics and trade-off analysis; "the hard parts" · [notes](notes/architecture-trade-offs-and-fitness-functions.md) · [Fundamentals of Software Architecture](https://fundamentalsofsoftwarearchitecture.com/) · [Software Architecture: The Hard Parts](https://www.oreilly.com/library/view/software-architecture-the/9781492086888/)
- [ ] 7.6 Evolutionary architecture and fitness functions · [notes](notes/architecture-trade-offs-and-fitness-functions.md) · [Building Evolutionary Architectures](https://evolutionaryarchitecture.com/)

### 8. API design

- [ ] 8.1 Designing an API as a product: consumers first, consistency, discoverability, documentation · [notes](notes/api-design-guidelines.md) · [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/)
- [ ] 8.2 Resource modelling, naming, errors, pagination, filtering, idempotency, versioning (mechanics in Web & HTTP) · [notes](notes/api-design-guidelines.md) · [Google API Improvement Proposals](https://google.aip.dev/) · [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines)
- [ ] 8.3 Contract-first with OpenAPI; generated clients and servers; consumer-driven contracts · [notes](notes/contract-testing-with-pact.md) · [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) · [Pact](https://docs.pact.io/)
- [ ] 8.4 Evolving APIs: additive changes, deprecation policy, `Sunset` and `Deprecation` headers, compatibility tests · [notes](notes/api-design-guidelines.md) · [Zalando guidelines: Compatibility](https://opensource.zalando.com/restful-api-guidelines/#compatibility)
- [ ] 8.5 Library and internal API design: minimal surface, immutability, naming, hard to misuse · [Joshua Bloch: How to Design a Good API and Why it Matters](https://www.youtube.com/watch?v=aAb7hSCtvGw)

### 9. Engineering communication

- [ ] 9.1 Design documents: problem, constraints, options considered, decision, risks; one page when possible · [notes](notes/design-docs-and-adrs.md) · [Malte Ubl: Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/)
- [ ] 9.2 Architecture Decision Records: when to write one, the template, keeping them alive · [notes](notes/design-docs-and-adrs.md) · [ADR GitHub organisation](https://adr.github.io/) · [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ ] 9.3 Diagrams that communicate: the C4 model, sequence diagrams, diagrams as code in the repo · [notes](notes/c4-diagrams-and-technical-writing.md) · [C4 model](https://c4model.com/) · [Mermaid](https://mermaid.js.org/)
- [ ] 9.4 Code review that helps: what to look for, how to comment, how to receive feedback, review turnaround · [notes](notes/code-review-that-helps.md) · [Google: Code Review Developer Guide](https://google.github.io/eng-practices/review/) · [Google: The Change Author's Guide](https://google.github.io/eng-practices/review/developer/)
- [ ] 9.5 Technical writing: clear sentences, structure, writing for the reader who skims · [notes](notes/c4-diagrams-and-technical-writing.md) · [Google: Technical Writing Courses](https://developers.google.com/tech-writing)
- [ ] 9.6 Estimation and planning: breaking work down, confidence ranges, surfacing risk early, saying no · [notes](notes/estimation-and-saying-no.md) · [Jacob Kaplan-Moss: Software Estimation Is Hard](https://jacobian.org/2021/may/20/estimation/)

## Resources

### Start here

- [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php) · John Ousterhout. Short, opinionated, and the best modern book on what good design actually is (paid).
- [refactoring.guru](https://refactoring.guru/) · free, visual catalogue of design patterns, code smells and refactorings, with Java examples.
- [Ham Vocke: The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) · the testing strategy article to read before any other.
- [Herberto Graça: Explicit Architecture](https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/) · how DDD, hexagonal, onion, clean and CQRS fit together.
- [Google Engineering Practices](https://google.github.io/eng-practices/) · the code review guide, for both reviewers and authors.

### Books

- [Refactoring, 2nd edition](https://refactoring.com/) · Martin Fowler (paid).
- [Working Effectively with Legacy Code](https://www.oreilly.com/library/view/working-effectively-with/0131177052/) · Michael Feathers (paid).
- [Unit Testing Principles, Practices, and Patterns](https://www.manning.com/books/unit-testing) · Vladimir Khorikov; the clearest book on what to test and how (paid).
- [Growing Object-Oriented Software, Guided by Tests](http://www.growing-object-oriented-software.com/) · Freeman and Pryce (paid).
- [Domain-Driven Design](https://www.domainlanguage.com/ddd/) · Eric Evans (paid); the free [DDD Reference](https://www.domainlanguage.com/ddd/reference/) summarises the patterns.
- [Learning Domain-Driven Design](https://www.oreilly.com/library/view/learning-domain-driven-design/9781098100124/) · Vlad Khononov; the most approachable DDD book (paid).
- [Fundamentals of Software Architecture](https://fundamentalsofsoftwarearchitecture.com/) · Richards and Ford (paid).
- [Design Patterns](https://www.oreilly.com/library/view/design-patterns-elements/0201633612/) · Gamma, Helm, Johnson, Vlissides (paid); or the friendlier [Head First Design Patterns](https://www.oreilly.com/library/view/head-first-design/9781492077992/).
- [The Pragmatic Programmer, 20th anniversary edition](https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/) · Hunt and Thomas (paid).
- [Clean Code](https://www.oreilly.com/library/view/clean-code-a/9780136083238/) · Robert C. Martin (paid). Still useful on naming and functions; read Ousterhout alongside for a counterweight.

### Courses and videos

- [John Ousterhout: A Philosophy of Software Design](https://www.youtube.com/watch?v=bmSAYlu0NcY) · the one-hour version of the book.
- [Kevlin Henney](https://www.youtube.com/results?search_query=kevlin+henney) · talks on code, naming and design that reward repeat viewing.
- [Sandi Metz: All the Little Things](https://www.youtube.com/watch?v=8bZh5LMaSmE) · refactoring a gnarly conditional live; Ruby, but the lesson is universal.
- [GOTO Conferences](https://www.youtube.com/@GOTO-) · architecture and craft talks from practitioners.
- [CodeAesthetic](https://www.youtube.com/@CodeAesthetic) · short, well-produced videos on readable code.

### References

- [Martin Fowler's bliki](https://martinfowler.com/bliki/) · definitions for most architecture vocabulary.
- [Java Design Patterns](https://java-design-patterns.com/) · patterns implemented in Java with explanations.
- [C4 model](https://c4model.com/) and [ADR](https://adr.github.io/) · diagramming and decision records.
- [DDD Crew](https://github.com/ddd-crew) · templates for bounded context canvases and other DDD workshops.
- [roadmap.sh: Software Design and Architecture](https://roadmap.sh/software-design-architecture) · visual overview.
