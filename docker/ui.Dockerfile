FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --create-home app
WORKDIR /ui
COPY ui/requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=app:app ui/streamlit_app.py .
USER 10001
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
