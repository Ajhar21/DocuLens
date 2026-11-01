@echo off
echo === 1. import check
python -c "import app.main, app.worker" || goto :fail
echo === 2. tests (verbose, show skips)
python -m pytest -v --tb=short -rs || goto :fail
echo === 3. migration round trip
alembic upgrade head || goto :fail
alembic downgrade -1 || goto :fail
alembic upgrade head || goto :fail
alembic current
echo === ALL OK
exit /b 0
:fail
echo === FAILED
exit /b 1