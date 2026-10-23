# Storage options: object, block and file storage, tiers, lifecycle rules and presigned URLs

> **In one sentence:** Object storage is an HTTP API over unlimited, durable, strongly consistent blobs billed per byte and per request; block storage is a disk attached to one VM in one zone billed per provisioned byte; file storage is a shared filesystem billed per byte used or provisioned; and most application data belongs in the first, behind lifecycle rules and presigned URLs.

**Why it matters:** Uploads, exports, backups and logs are the bulk of a system's bytes, and putting them on the wrong storage type costs money or availability: a disk that dies with its zone, an API that proxies gigabytes through a 2 GiB container, a bucket of ten-year-old thumbnails in the most expensive tier. Presigned URLs and lifecycle rules are two small tools that fix most of it.

## The idea

### Three kinds of storage

| Kind | AWS | Azure | What it is | Attached to | Pay for |
|---|---|---|---|---|---|
| Object | S3 | Blob Storage | Flat namespace of keys (prefixes look like folders), accessed over HTTPS, replicated across zones, effectively unlimited | Anything with credentials and a network path | GB-month per tier, requests, retrieval for cold tiers, egress |
| Block | EBS | Managed Disks | A raw disk with a filesystem of your choice; lives in one zone (zone-redundant disk options exist on Azure) | One VM at a time | Provisioned GB-month plus provisioned performance, whether or not the disk is full or even attached |
| File | EFS, FSx | Azure Files | A shared filesystem over NFS or SMB mounted by many instances | Many VMs or containers at once | GB used (EFS, Azure Files standard) or provisioned (Azure Files premium), plus throughput |

Both S3 and Blob Storage are **strongly consistent**: a read after a successful write returns the new object, and a list after a write includes it. That has been true for S3 since December 2020, so older advice about eventual consistency in S3 is obsolete.

### Tiers and the cost structure

| Dimension | S3 | Blob Storage |
|---|---|---|
| Hot | Standard | Hot |
| Automatic | Intelligent-Tiering moves objects between tiers by access | Lifecycle rules by last access time (access tracking must be enabled) |
| Infrequent | Standard-IA, One Zone-IA (30-day minimum charge) | Cool (30-day early-deletion charge) |
| Cold | Glacier Instant Retrieval (90-day minimum, instant) | Cold (90-day early-deletion charge) |
| Archive | Glacier Flexible Retrieval (90-day minimum, minutes to hours), Glacier Deep Archive (180-day minimum, hours) | Archive (180-day early-deletion charge; a blob must be rehydrated, taking hours, before it can be read) |

The cost structure is what to internalise, not the prices. Hot tiers charge mostly for **bytes stored**; cold tiers charge less per byte but add **retrieval per GB**, **minimum storage durations** and, for archives, hours of latency. Every tier charges per **request**, and writes and lists cost more than reads. Egress to the internet is billed separately. A million tiny objects can cost more in requests than in bytes; an archive you read monthly costs more than leaving it in a cooler hot tier.

### Lifecycle rules and versioning

**Lifecycle rules** move or delete objects by age without any code: transition to a cooler tier after N days, expire after M days, clean up old versions and abandoned multipart uploads. **Versioning** keeps every overwrite and delete as a recoverable version (S3 versioning; Blob versioning plus soft delete), which is cheap protection against bugs and ransomware, and which also means deletes do not free space until a lifecycle rule expires the old versions.

### Presigned URLs

A **presigned URL** (S3) or a **shared access signature** (Blob Storage; prefer a *user delegation SAS*, signed with an Entra identity rather than an account key) is a URL that carries a signature granting one operation on one object for a limited time. Your API decides who may upload what, mints the URL, and the client talks to the storage service directly. The bytes never pass through your JVM. S3 signatures made with role credentials are valid at most as long as the credentials; signatures made with long-lived IAM user keys may last up to seven days, which is longer than you want.

## Example: an upload flow and the lifecycle rules behind it

The flow: the client asks the API for an upload URL; the API checks authorisation, chooses a key under its own prefix, mints a URL valid for ten minutes that allows exactly one `PUT` with a fixed content type; the client `PUT`s the file; the client tells the API it is done (or the API listens for the bucket's object-created event, see item 7.1); the API records the key.

```java
import java.net.URL;
import java.time.Duration;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

public final class UploadUrlService {

    private final S3Presigner presigner;
    private final String bucketName;

    public UploadUrlService(S3Presigner presigner, String bucketName) {
        this.presigner = presigner;
        this.bucketName = bucketName;
    }

    public URL createUploadUrl(String objectKey, String contentType) {
        PutObjectRequest putObjectRequest = PutObjectRequest.builder()
                .bucket(bucketName)
                .key(objectKey)
                .contentType(contentType)
                .build();
        PutObjectPresignRequest presignRequest = PutObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .putObjectRequest(putObjectRequest)
                .build();
        PresignedPutObjectRequest presignedRequest = presigner.presignPutObject(presignRequest);
        return presignedRequest.url();
    }
}
```

The client then uploads with the same content type, because it was signed:

```bash
curl --fail -X PUT -H "Content-Type: image/png" --upload-file photo.png "$UPLOAD_URL"
```

Change the header or the key and S3 answers `403 SignatureDoesNotMatch`. The `S3Presigner` is built once with the default credential chain, so in production it signs with the task role (see item 2.2). The Azure equivalent obtains a user delegation key from the `BlobServiceClient`, builds `BlobServiceSasSignatureValues` with a ten-minute expiry and write-only permission, and calls `generateUserDelegationSas` on the `BlobClient`; the client uploads with `PUT` and the `x-ms-blob-type: BlockBlob` header.

The lifecycle configuration for the same bucket, as the AWS CLI accepts it:

```json
{
  "Rules": [
    {
      "ID": "uploads-tiering-and-cleanup",
      "Filter": { "Prefix": "uploads/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" },
        { "Days": 90, "StorageClass": "GLACIER_IR" }
      ],
      "Expiration": { "Days": 365 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
    }
  ]
}
```

Read it as a policy: uploads are hot for a month, infrequent-access for two, instantly retrievable cold storage for the rest of the year, then gone; overwritten versions survive thirty days for recovery; half-finished multipart uploads, which are invisible in listings but billed, are cleaned up after a week. The Azure lifecycle management policy expresses the same with `tierToCool` at 30 days, `tierToCold` at 90, `delete` at 365 (using `daysAfterModificationGreaterThan`), plus a rule deleting previous versions after 30 days.

## Pitfalls

- Proxying uploads and downloads through the API. Memory, bandwidth and request threads are spent on bytes the storage service would have handled directly; use presigned URLs.
- Archive tiers for data you read regularly. Retrieval fees and minimum durations make it dearer than a hot tier, and archive reads take hours.
- Lifecycle rules without `AbortIncompleteMultipartUpload`. Failed large uploads sit in the bucket, billed and invisible.
- Versioning without version expiry. Deleting is now free of charge in effect and the bucket only grows.
- Block storage for shared or durable data. A disk is tied to one VM and one zone; when the zone or the VM goes, the data is unreachable until you restore a snapshot.
- Paying for unattached disks. The VM is gone, the disk is not; both clouds bill the provisioned size regardless (see item 5.7).
- Presigned URLs that allow more than intended: no content type, a long expiry, or a key the client chose. Sign the exact operation you authorised.
- Millions of tiny objects. Request charges dominate; batch small records into larger objects or use a database.

## Check yourself

1. A customer uploads a 2 GB video through your Spring API running in a 2 GiB container. What fails, and what does the flow look like after the fix on each cloud?
2. Why is "the URL is HTTPS, so it is fine" the wrong frame for a presigned URL, and which three things should the signature pin down?
3. A bucket holds daily database exports read once a quarter for audits, kept seven years. Choose tiers and lifecycle transitions and explain the retrieval and minimum-duration trade-offs.
4. Your monthly S3 bill is dominated by request charges rather than storage. What does that tell you about the data, and what are two ways to restructure it?

## Go deeper

- [Amazon S3 storage classes](https://aws.amazon.com/s3/storage-classes/) · the tiers, minimum durations and retrieval models in one table.
- [Azure Blob Storage: Access tiers](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview) · hot, cool, cold and archive with the early-deletion and rehydration rules.
- [Amazon S3: Sharing objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html) · how signatures are built, what they pin and how long they can last.
- [Azure Storage: Grant limited access with shared access signatures](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview) · service, account and user delegation SAS, and why the last is recommended.

---

Part of [Cloud](../README.md) · item 6.1
