from flask import Blueprint, render_template

# 建立藍圖
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """主頁面"""
    return render_template('index.html')

@main_bp.route('/meeting-minutes')
def meeting_minutes():
    """會議紀錄模板生成頁面"""
    return render_template('meeting_minutes.html') 