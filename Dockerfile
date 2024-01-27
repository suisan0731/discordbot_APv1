FROM python:3.11
WORKDIR /bot
COPY requirements.txt /bot/
RUN pip install -r requirements.txt
RUN curl -OL https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip
RUN unzip -o ./ffmpeg-master-latest-win64-gpl-shared.zip
RUN cp -r ./ffmpeg-master-latest-win64-gpl-shared/bin ./
RUN rm -dr ./ffmpeg-master-latest-win64-gpl-shared
COPY . /bot
CMD python main.py