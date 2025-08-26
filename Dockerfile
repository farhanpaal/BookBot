FROM python:3.10.8-slim-bullseye

RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends git ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt

RUN cd /
RUN pip3 install -U pip && pip3 install -U -r requirements.txt
RUN mkdir /Advance-AutoFilter-bot
WORKDIR /Advance-AutoFilter-bot
COPY . /Advance-AutoFilter-bot
CMD ["python", "bot.py"]
