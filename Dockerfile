# slim variant keeps the image small — no compiler toolchain needed since
# all our dependencies (groq, django, sqlparse) are pure Python or ship wheels.
FROM python:3.11-slim

WORKDIR /app

# Copy only requirements first so Docker's layer cache is reused on rebuilds
# where dependencies haven't changed — only the final COPY . . layer rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the source tree (agent, chat app, eval harness, etc.)
COPY . .

# Bake the seeded SQLite DB into the image at build time — db/ecommerce.db is
# gitignored, so without this step the container would have no data at all.
RUN python db/seed.py

EXPOSE 8000

# Shell form (not exec form) so ${PORT} expands — Railway/Render/most PaaS
# hosts assign their own port at runtime and won't necessarily use 8000.
CMD python manage.py runserver 0.0.0.0:${PORT:-8000}
