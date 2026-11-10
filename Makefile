.PHONY: test validate smoke table demo
test:
	python -m pytest -q
validate:
	scopeguard validate
smoke:  # full pipeline on the SIMULATED agent (not results)
	scopeguard run --exp E3 --agent sim --seeds 2 --exploratory --out results/smoke
table:
	scopeguard table --in results/smoke/E3.jsonl
demo:
	scopeguard demo --out demo/index.html
