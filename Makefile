# .PHONY declares these as commands, not files — `make seed` always runs even
# if a file literally named "seed" happens to exist in this directory.
.PHONY: setup seed run eval docker-up docker-down

setup:                              # one-time: install all Python dependencies
	pip install -r requirements.txt

seed:                                # (re)create db/ecommerce.db with fresh sample data
	python db/seed.py

run: seed                           # reseed, then start the Django dev server
	@echo "Starting Django on http://localhost:8000"
	python manage.py runserver 8000

eval: seed                          # reseed, then run the 10-question gold-query benchmark
	python eval/evaluate.py

docker-up:                          # build the image (which seeds the DB) and start the container
	docker-compose up --build

docker-down:                        # stop and remove the running container
	docker-compose down
