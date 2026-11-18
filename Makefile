.PHONY: test a b all zero-a

test:
	pytest -q

a:
	python -m spend_pipeline --config configs/company_a.yaml --output outputs/shivani_mishra__A.csv --diagnostics outputs/A_diagnostics.json

b:
	python -m spend_pipeline --config configs/company_b.yaml --output outputs/shivani_mishra__B.csv --diagnostics outputs/B_diagnostics.json

all: test a b

zero-a:
	python -m spend_pipeline.evaluate --config configs/company_a.yaml
