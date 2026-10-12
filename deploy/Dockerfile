# Crafter gateway image: Python FastMCP gateway + pilot CLI install hooks.
#
# The pilot Craft CLIs (photocraft-cli, pdfcraft-cli, gridcraft-cli) are not
# public packages yet — install them in the builder stage when available
# (uncomment the COPY/RUN lines and point at the release zips). Without them
# the gateway runs in fake-backend mode (documented fallback, all tools work,
# real-CLI proxy path unexercised).

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# --- pilot CLI install hooks (uncomment when release zips are available) ---
# COPY dist/photocraft-cli dist/pdfcraft-cli dist/gridcraft-cli /tmp/clis/
# RUN for cli in photocraft pdfcraft gridcraft; do \
#       unzip -o /tmp/clis/${cli}-cli-*.zip -d /usr/local/bin/ && \
#       chmod +x /usr/local/bin/${cli}-cli; \
#     done && rm -rf /tmp/clis/
# --- end pilot CLI hooks ---

COPY gateway/requirements.txt ./gateway/requirements.txt
RUN pip install --no-cache-dir -r gateway/requirements.txt

COPY gateway/ ./gateway/

# Non-root runtime user; the work dir is mounted by compose.
RUN useradd --create-home --uid 10001 crafter \
    && mkdir -p /work && chown crafter:crafter /work
USER crafter

EXPOSE 8787

# Default: streamable_http on :8787 (bearer enforced; tokens via env/secret).
ENTRYPOINT ["python", "-m", "gateway.main"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8787", "--path", "/mcp"]
