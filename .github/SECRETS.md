# Required GitHub Actions Secrets

Configure these secrets in **Settings → Secrets and variables → Actions**
before the CI pipeline will pass.

| Secret Name         | Description                                          | Example / Format               |
|---------------------|------------------------------------------------------|--------------------------------|
| `OPENAI_API_KEY`    | OpenAI API key for GPT-4o LLM calls                 | `sk-proj-...`                  |
| `DEEPSEEK_API_KEY`  | DeepSeek API key (ARM thinking engine)               | `ds-...`                       |
| `SECRET_KEY`        | FastAPI JWT signing secret (min 32 chars)            | random hex string              |
| `PERMISSION_SECRET` | Permission validation secret                         | random hex string              |
| `AINDY_API_KEY`     | Internal AINDY API key for service-to-service calls | random hex string              |
| `DATABASE_URL`      | PostgreSQL connection string with pgvector           | `postgresql://user:pw@host/db` |
| `MONGO_URL`         | MongoDB connection string                            | `mongodb://host:27017`         |
| `ALLOWED_ORIGINS`   | CORS allowed origins (comma-separated)               | `https://yourdomain.com`       |

> **Note:** For CI, `DATABASE_URL` and `MONGO_URL` are provided via the service
> container configuration in `.github/workflows/ci.yml` and do **not** need to
> be set as secrets. The other keys use placeholder values during test runs —
> all external API calls are mocked in the test suite.

## Codecov (Optional)

| Secret Name      | Description               |
|------------------|---------------------------|
| `CODECOV_TOKEN`  | Upload token from codecov.io for coverage badges |

## Generating Secrets Locally

```bash
# Generate a secure SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```
