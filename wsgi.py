"""Ponto de entrada de produção: gunicorn wsgi:app"""
from app import create_app

app = create_app()
