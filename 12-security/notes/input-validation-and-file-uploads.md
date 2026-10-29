# Input validation and file-upload safety as a system

> **In one sentence:** Validation is the layer that rejects input which cannot be legitimate (wrong type, length, range, shape, or a file that is not what it claims to be) before it travels anywhere, and it works only as a system: limits at the edge, allow-lists at the boundary, business rules in the service, canonicalisation before every check, and never as a substitute for parameterised queries and output encoding.

**Why it matters:** Most injection and traversal bugs are reachable because something accepted a value that no legitimate client would ever send: a 40 MB "avatar", a username with a newline, a file name with `../`, a page size of a million. Validation does not fix SQL injection or XSS (prepared statements and encoding do, items 2.3 and 2.10), but it shrinks the attack surface so that the remaining defences are only ever tested by plausible input. File uploads are where all of this concentrates: one endpoint that receives bytes, names, types and sizes from a stranger and stores them where other users will fetch them.

## The idea

Three defences are easy to confuse because they all touch the same input:

| Defence | Question it answers | Where | Example |
|---|---|---|---|
| Validation | Could this value be legitimate at all? | At the boundary, before use | An email has one `@`, is under 254 characters; a quantity is 1 to 100 |
| Parameterisation | How do I pass data to an interpreter without it becoming code? | Every query, command, LDAP filter | `PreparedStatement`, `ProcessBuilder` with an argument list |
| Output encoding | How do I write data into a document without it becoming markup? | Every template, every context | `th:text`, `Encode.forHtml` |

Validation is the only one of the three that rejects. The other two make any value safe to pass along. A valid-looking name such as `O'Brien` must survive all three, which is why validation cannot be "reject quotes".

**Layers, from the edge inward.**

1. **Transport limits.** The container refuses what the application should never have to look at: request header size, body size, multipart size and file count, connection and read timeouts. These are properties, not code.
2. **Syntactic validation at the boundary.** Type, length, range, character set and format, as allow-lists: "a locale is two lower-case letters optionally followed by a dash and two upper-case letters", not "contains no `<`". Bean Validation annotations on request records, triggered by `@Valid`. Unknown JSON fields either rejected or ignored, never bound onto something that matters (item 2.12).
3. **Semantic validation in the service.** Rules that need more than the value: the referenced product exists and belongs to this tenant, the date is after the start date, the discount does not exceed the user's limit. This is also where authorization lives (item 4.2), which is why it cannot be an annotation.
4. **Canonicalise before you check.** Decode once (URL-encoding, base64), normalise Unicode so that visually identical strings compare equal, resolve `.` and `..` in paths, lower-case the domain part of an email, strip the trailing dot from a hostname. A check that runs on the raw form is bypassed by the encoded form; a check that runs after double-decoding is bypassed by single encoding. Decode exactly once, then validate, then use.
5. **Reject, do not repair.** Silently stripping characters produces values the user did not send and the attacker can predict (`<scr<script>ipt>` survives one pass of "remove `<script>`"). The one exception is rich text, which is sanitised with an allow-list sanitiser (item 2.10).

**File uploads** are a boundary with six separate properties to check:

| Property | Rule |
|---|---|
| Size and count | Hard maximum per file and per request, set at the container; a lower one in code for the specific endpoint |
| Name | Never used. Generate a UUID; keep the original only as display metadata, encoded on output |
| Extension | Allow-list, lower-cased, taken from the last dot only; `shell.jsp.png` is `png` and still has to pass the content check |
| Content | The first bytes match the type the extension promises (PNG, JPEG, PDF, ZIP all have fixed signatures); the client's `Content-Type` header is an opinion, not a fact |
| Location | Outside the web root, or in object storage; never under a directory a servlet container can execute from |
| Serving | `Content-Disposition: attachment` with a safe file name, `X-Content-Type-Options: nosniff`, a `Content-Type` you set from the stored type, ideally from a separate origin so a crafted file cannot run in your site's context |

Images deserve one more step: re-encode them (decode with `ImageIO`, write a new file) so that a file which is both a valid PNG and a valid script or HTML document (a polyglot) loses its second nature. SVG is XML that can contain script; treat it as text to sanitise, or convert it. Archives need a cap on entry count and total uncompressed size (a 42 KB zip bomb expands to petabytes) and the same path check per entry (`zip slip`: an entry named `../../etc/cron.d/job`).

## Example: a validator that runs as written

The checks in the table above, as one class, with the attempts an attacker would make:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public final class UploadValidator {

    private static final long MAX_SIZE_BYTES = 5L * 1024 * 1024;
    private static final Set<String> ALLOWED_EXTENSIONS = Set.of("png", "jpg", "jpeg", "pdf");
    private static final Map<String, byte[]> MAGIC_BYTES = Map.of(
            "png", HexFormat.of().parseHex("89504e470d0a1a0a"),
            "jpg", HexFormat.of().parseHex("ffd8ff"),
            "jpeg", HexFormat.of().parseHex("ffd8ff"),
            "pdf", "%PDF-".getBytes());

    private final Path uploadDirectory;

    public UploadValidator(Path uploadDirectory) {
        this.uploadDirectory = uploadDirectory.toAbsolutePath().normalize();
    }

    public Path store(String clientFileName, byte[] content) throws IOException {
        if (content.length == 0 || content.length > MAX_SIZE_BYTES) {
            throw new IllegalArgumentException("size " + content.length + " outside 1.." + MAX_SIZE_BYTES);
        }
        String extension = extensionOf(clientFileName)
                .filter(ALLOWED_EXTENSIONS::contains)
                .orElseThrow(() -> new IllegalArgumentException("extension not allowed: " + clientFileName));
        byte[] expectedPrefix = MAGIC_BYTES.get(extension);
        byte[] actualPrefix = Arrays.copyOf(content, expectedPrefix.length);
        if (!Arrays.equals(expectedPrefix, actualPrefix)) {
            throw new IllegalArgumentException("content does not look like " + extension);
        }
        Path target = uploadDirectory.resolve(UUID.randomUUID() + "." + extension);
        return Files.write(target, content);
    }

    public Path resolveStored(String storedName) {
        Path target = uploadDirectory.resolve(storedName).normalize();
        if (!target.startsWith(uploadDirectory) || target.equals(uploadDirectory)) {
            throw new IllegalArgumentException("path escapes upload directory: " + storedName);
        }
        return target;
    }

    private static Optional<String> extensionOf(String fileName) {
        int dot = fileName.lastIndexOf('.');
        if (dot < 0 || dot == fileName.length() - 1) {
            return Optional.empty();
        }
        return Optional.of(fileName.substring(dot + 1).toLowerCase());
    }

    public static void main(String[] arguments) throws IOException {
        UploadValidator validator = new UploadValidator(Files.createTempDirectory("uploads"));
        byte[] realPng = HexFormat.of().parseHex("89504e470d0a1a0a0000000d49484452");
        byte[] htmlDisguisedAsPng = "<script>alert(1)</script>".getBytes();
        attemptStore(validator, "avatar.png", realPng);
        attemptStore(validator, "avatar.png", htmlDisguisedAsPng);
        attemptStore(validator, "shell.jsp", realPng);
        attemptStore(validator, "shell.jsp.png", htmlDisguisedAsPng);
        attemptStore(validator, "big.png", new byte[6 * 1024 * 1024]);
        attemptResolve(validator, "1f9ba688-c0bd-477f-bdeb-31f2ffab6952.png");
        attemptResolve(validator, "../../etc/passwd");
    }

    private static void attemptStore(UploadValidator validator, String fileName, byte[] content) {
        try {
            Path stored = validator.store(fileName, content);
            System.out.println("stored   " + fileName + " as " + stored.getFileName());
        } catch (IllegalArgumentException | IOException exception) {
            System.out.println("rejected " + fileName + ": " + exception.getMessage());
        }
    }

    private static void attemptResolve(UploadValidator validator, String storedName) {
        try {
            System.out.println("resolved " + storedName + " to " + validator.resolveStored(storedName).getFileName());
        } catch (IllegalArgumentException exception) {
            System.out.println("rejected " + exception.getMessage());
        }
    }
}
```

```text
stored   avatar.png as 281365ca-260c-49f8-a1a1-4e7955200149.png
rejected avatar.png: content does not look like png
rejected shell.jsp: extension not allowed: shell.jsp
rejected shell.jsp.png: content does not look like png
rejected big.png: size 6291456 outside 1..5242880
resolved 1f9ba688-c0bd-477f-bdeb-31f2ffab6952.png to 1f9ba688-c0bd-477f-bdeb-31f2ffab6952.png
rejected path escapes upload directory: ../../etc/passwd
```

`store` never resolves the client's name against the file system at all, which is the strongest traversal defence. `resolveStored` is for the download side, where a name does come from the request: `normalize()` collapses the `..` segments and `startsWith` on the normalised absolute path is the check. The magic-byte check is deliberately simple; Apache Tika does the same for hundreds of types if you need them.

## Example: the Spring side

The container limits, set once:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
server.max-http-request-header-size=16KB
```

A request record whose annotations are allow-lists, and a controller that validates it and hands the file to the class above:

```java
public record CreateDocumentRequest(
        @NotBlank @Size(max = 120) String title,
        @NotNull @Pattern(regexp = "^[a-z]{2}(-[A-Z]{2})?$") String locale) {
}

@RestController
public class DocumentController {

    private final UploadValidator uploadValidator;

    public DocumentController(UploadValidator uploadValidator) {
        this.uploadValidator = uploadValidator;
    }

    @PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Void> upload(@Valid @RequestPart("metadata") CreateDocumentRequest metadata,
                                       @RequestPart("file") MultipartFile file) throws IOException {
        Path stored = uploadValidator.store(file.getOriginalFilename(), file.getBytes());
        return ResponseEntity.created(URI.create("/documents/" + stored.getFileName())).build();
    }

    @GetMapping("/documents/{storedName}")
    public ResponseEntity<Resource> download(@PathVariable String storedName) {
        Path path = uploadValidator.resolveStored(storedName);
        ContentDisposition disposition = ContentDisposition.attachment()
                .filename(path.getFileName().toString(), StandardCharsets.UTF_8)
                .build();
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .header("X-Content-Type-Options", "nosniff")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(new FileSystemResource(path));
    }
}
```

A `@Valid` failure becomes `MethodArgumentNotValidException` and a `400`; the container's size limit becomes `MaxUploadSizeExceededException`. Both deserve a handler that returns a short, generic message and logs the field names but never the values.

## Pitfalls

- Validating before decoding. `%2e%2e%2f` passes a check for `../` and becomes `../` one layer down.
- Deny-lists of extensions. `.jsp`, `.jspx`, `.phtml`, `.svg`, `.html`, `.htm`, `.xhtml`, `.shtml`: the list is never complete. Allow the three types you need.
- Trusting `Content-Type` from the multipart part, or `Files.probeContentType`, which asks the operating system and varies by host.
- Storing uploads under the application's static resources or a servlet-executable path. A `.jsp` that passed as `.png` is now code.
- The original file name in `Content-Disposition` without encoding. A name with `"; filename=` or a newline forges headers; let `ContentDisposition` build it.
- Annotations without `@Valid`. The record is annotated, nothing runs. For method parameters in services, `@Validated` on the class is needed too.
- Regular expressions with nested quantifiers on user input (`^(a+)+$`). Catastrophic backtracking turns a 30-character string into a CPU denial of service; keep patterns linear or bound the input length first.
- Reading the whole upload into memory before checking its size. Check `file.getSize()` or stream to a size-limited sink; the container limit is the backstop, not the implementation.

## Check yourself

1. Why does rejecting `'` in a name field not protect against SQL injection, and what does?
2. A reviewer suggests `if (fileName.contains(".."))` as the traversal check. Give two inputs that defeat it and the check that does not.
3. The upload endpoint checks extension and magic bytes but stores files under `/static/uploads/`. What attack remains, and which row of the file-upload table did it violate?
4. Where in the layers does "the referenced invoice must belong to the caller's tenant" belong, and why can it not be a Bean Validation annotation?

## Go deeper

- [OWASP: Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) · allow-lists, canonicalisation, and the file-upload section in brief.
- [OWASP: File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) · the full list of upload checks, including image re-encoding and archive handling.
- [OWASP: Bean Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bean_Validation_Cheat_Sheet.html) · annotations, `@Valid` placement and custom constraints in a Spring application.
- [Spring Framework: Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html) · `MultipartFile`, `@RequestPart` and the exceptions involved.
- [Snyk: Zip Slip](https://security.snyk.io/research/zip-slip-vulnerability) · the archive traversal class of bug, with the libraries that had it.
- [Jakarta Bean Validation](https://beanvalidation.org/) · the specification behind the annotations.

---

Part of [Security](../README.md) · item 9.5
