.PHONY: setup seed run eval docker-up docker-down

setup:
	pip install -r requirements.txt

seed:
	python db/seed.py

run: seed
	@echo "Starting Django on http://localhost:8000"
	python manage.py runserver 8000

eval: seed
	python eval/evaluate.py

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down
