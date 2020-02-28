FROM python:3
ENV PYTHONUNBUFFERED 1
RUN mkdir /code
WORKDIR /code
COPY ./new /code/
RUN pip install -r requirements.txt
#CMD ["python /code/tidebilling/manage.py runserver 0.0.0.0:8000"]