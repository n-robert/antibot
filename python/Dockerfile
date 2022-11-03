FROM python
WORKDIR /tmp
RUN pip install psycopg2-binary python-dotenv telethon apscheduler sqlalchemy
ADD requirements.txt requirements.txt
RUN pip freeze > requirements.txt
COPY . ./
CMD ["python", "-u", "main.py"]