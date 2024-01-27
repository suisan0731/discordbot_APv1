FROM python:3.11
ENV DISCORD_TOKEN=MTE5NDY3NTIxMDcyMTQ0ODA5Nw.GDCkoZ.MghCMKFrPBX0KuzUD4RlhcVBY8lVrQSPAB1G2g
WORKDIR /bot
COPY requirements.txt /bot/
RUN pip install -r requirements.txt
COPY . /bot
CMD python main.py