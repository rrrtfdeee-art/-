FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# نسخCOPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .


EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
