import os
import logging
from flask import Blueprint, render_template

# 建立藍圖
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """主頁面"""
    return render_template('index.html') 