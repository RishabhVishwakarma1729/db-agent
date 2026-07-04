FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python db/seed.py

EXPOSE 8000

# Shell form (not exec form) so ${PORT} expands — Railway assigns its own
# port at runtime and won't necessarily be 8000.
CMD python manage.py runserver 0.0.0.0:${PORT:-8000}
