# artifact-service

Provides artifact metadata + **presigned URLs** for MinIO/S3.

Endpoints:
- `POST /api/v1/artifacts` create an artifact record
- `POST /api/v1/artifacts/presign` create a presigned URL for PUT/GET

Env:
- `DATABASE_URL`
- `MINIO_ENDPOINT` (e.g. http://minio:9000)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `S3_REGION` (default us-east-1)

