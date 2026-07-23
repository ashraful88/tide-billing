# tide-billing
Invoice and subscriptions management


1. Orders => 2. Invoice => 3. Payments
    if Order type subscription => 2. Invoice recurring => Payment
    else done

## How to run locally

#### or run using python venv

```
python3 -m venv .venv
source .venv/bin/activate 
pip install --no-cache-dir -r requirements.txt
python manage.py runserver 0.0.0.0:8000
```

```
pip install pip-review
pip-review
```
