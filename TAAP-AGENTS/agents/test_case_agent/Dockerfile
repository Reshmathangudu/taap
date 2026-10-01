FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./test_case_agent

EXPOSE 8001

ENV A2A_HOST=0.0.0.0
ENV A2A_PORT=8001

CMD ["uvicorn", "test_case_agent.a2a_server:a2a_app", "--host", "0.0.0.0", "--port", "8001"]
