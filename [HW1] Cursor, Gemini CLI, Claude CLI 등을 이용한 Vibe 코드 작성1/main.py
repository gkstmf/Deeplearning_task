"""
앱 사용시간 추적 및 카카오톡 자동 전송 프로그램
- Windows 앱 사용시간 추적
- 월별, 주별, 일별 통계 그래프 생성
- 사용 성향 분석 및 요약
- 카카오톡 자동 전송
"""

import os
import sys
import time
import json
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import schedule

# GUI 및 그래프 라이브러리
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib import rcParams
try:
    import seaborn as sns
    SEABORN_AVAILABLE = True
except ImportError:
    SEABORN_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# Windows API
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# 카카오톡 API (추후 구현)
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

class AppUsageTracker:
    def __init__(self):
        self.db_path = "app_usage.db"
        self.current_app = None
        self.start_time = None
        self.running = False
        self.setup_database()
        self.setup_matplotlib()
        
    def setup_database(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                duration INTEGER NOT NULL,
                date DATE NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def setup_matplotlib(self):
        """한글 폰트 설정"""
        # Windows 기본 한글 폰트 설정
        plt.rcParams['font.family'] = 'Malgun Gothic'
        plt.rcParams['axes.unicode_minus'] = False
        
    def get_active_window_info(self):
        """현재 활성 창 정보 가져오기"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                app_name = process.name()
                window_title = win32gui.GetWindowText(hwnd)
                return app_name, window_title
        except:
            pass
        return None, None
        
    def save_usage_data(self, app_name, start_time, end_time):
        """사용 데이터 저장"""
        duration = int((end_time - start_time).total_seconds())
        if duration > 0:  # 0초 이상인 경우만 저장
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO app_usage (app_name, start_time, end_time, duration, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (app_name, start_time, end_time, duration, start_time.date()))
            
            conn.commit()
            conn.close()
            
    def track_usage(self):
        """앱 사용시간 추적"""
        print("앱 사용시간 추적을 시작합니다...")
        self.running = True
        
        while self.running:
            app_name, window_title = self.get_active_window_info()
            current_time = datetime.now()
            
            if app_name and app_name != self.current_app:
                # 이전 앱 사용시간 저장
                if self.current_app and self.start_time:
                    self.save_usage_data(self.current_app, self.start_time, current_time)
                
                # 새 앱 추적 시작
                self.current_app = app_name
                self.start_time = current_time
                print(f"현재 앱: {app_name}")
                
            time.sleep(1)  # 1초마다 체크
            
    def stop_tracking(self):
        """추적 중지"""
        self.running = False
        if self.current_app and self.start_time:
            self.save_usage_data(self.current_app, self.start_time, datetime.now())
            
    def get_usage_stats(self, days=7):
        """사용 통계 가져오기"""
        if not PANDAS_AVAILABLE:
            print("pandas가 설치되지 않아 통계를 가져올 수 없습니다.")
            return pd.DataFrame()  # 빈 DataFrame 반환
            
        conn = sqlite3.connect(self.db_path)
        
        # 지난 N일간의 데이터
        start_date = datetime.now().date() - timedelta(days=days-1)
        
        query = '''
            SELECT app_name, SUM(duration) as total_duration, date
            FROM app_usage 
            WHERE date >= ?
            GROUP BY app_name, date
            ORDER BY date DESC, total_duration DESC
        '''
        
        df = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()
        
        return df
        
    def create_daily_chart(self, save_path="daily_usage.png"):
        """일별 사용시간 차트 생성"""
        if not PANDAS_AVAILABLE:
            print("pandas가 설치되지 않아 차트를 생성할 수 없습니다.")
            return None
            
        df = self.get_usage_stats(days=7)
        
        if df.empty:
            return None
            
        # 일별 총 사용시간
        daily_total = df.groupby('date')['total_duration'].sum().reset_index()
        daily_total['hours'] = daily_total['total_duration'] / 3600
        
        plt.figure(figsize=(12, 6))
        plt.plot(daily_total['date'], daily_total['hours'], marker='o', linewidth=2, markersize=8)
        plt.title('일별 컴퓨터 사용시간', fontsize=16, fontweight='bold')
        plt.xlabel('날짜', fontsize=12)
        plt.ylabel('사용시간 (시간)', fontsize=12)
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return save_path
        
    def create_weekly_chart(self, save_path="weekly_usage.png"):
        """주별 사용시간 차트 생성"""
        if not PANDAS_AVAILABLE:
            print("pandas가 설치되지 않아 차트를 생성할 수 없습니다.")
            return None
            
        df = self.get_usage_stats(days=28)  # 4주간
        
        if df.empty:
            return None
            
        df['date'] = pd.to_datetime(df['date'])
        df['week'] = df['date'].dt.isocalendar().week
        df['year'] = df['date'].dt.year
        df['week_label'] = df['year'].astype(str) + '-W' + df['week'].astype(str)
        
        weekly_total = df.groupby('week_label')['total_duration'].sum().reset_index()
        weekly_total['hours'] = weekly_total['total_duration'] / 3600
        
        plt.figure(figsize=(12, 6))
        plt.bar(weekly_total['week_label'], weekly_total['hours'], color='skyblue', alpha=0.8)
        plt.title('주별 컴퓨터 사용시간', fontsize=16, fontweight='bold')
        plt.xlabel('주차', fontsize=12)
        plt.ylabel('사용시간 (시간)', fontsize=12)
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return save_path
        
    def create_monthly_chart(self, save_path="monthly_usage.png"):
        """월별 사용시간 차트 생성"""
        if not PANDAS_AVAILABLE:
            print("pandas가 설치되지 않아 차트를 생성할 수 없습니다.")
            return None
            
        conn = sqlite3.connect(self.db_path)
        
        query = '''
            SELECT 
                strftime('%Y-%m', date) as month,
                app_name,
                SUM(duration) as total_duration
            FROM app_usage 
            WHERE date >= date('now', '-6 months')
            GROUP BY month, app_name
            ORDER BY month DESC, total_duration DESC
        '''
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return None
            
        monthly_total = df.groupby('month')['total_duration'].sum().reset_index()
        monthly_total['hours'] = monthly_total['total_duration'] / 3600
        
        plt.figure(figsize=(12, 6))
        plt.bar(monthly_total['month'], monthly_total['hours'], color='lightcoral', alpha=0.8)
        plt.title('월별 컴퓨터 사용시간', fontsize=16, fontweight='bold')
        plt.xlabel('월', fontsize=12)
        plt.ylabel('사용시간 (시간)', fontsize=12)
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return save_path
        
    def create_app_usage_chart(self, save_path="app_usage.png"):
        """앱별 사용시간 차트 생성"""
        if not PANDAS_AVAILABLE:
            print("pandas가 설치되지 않아 차트를 생성할 수 없습니다.")
            return None
            
        df = self.get_usage_stats(days=7)
        
        if df.empty:
            return None
            
        app_total = df.groupby('app_name')['total_duration'].sum().reset_index()
        app_total = app_total.sort_values('total_duration', ascending=False).head(10)
        app_total['hours'] = app_total['total_duration'] / 3600
        
        plt.figure(figsize=(12, 8))
        plt.barh(app_total['app_name'], app_total['hours'], color='lightgreen', alpha=0.8)
        plt.title('주간 앱별 사용시간 (상위 10개)', fontsize=16, fontweight='bold')
        plt.xlabel('사용시간 (시간)', fontsize=12)
        plt.ylabel('앱 이름', fontsize=12)
        plt.grid(True, alpha=0.3, axis='x')
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return save_path
        
    def analyze_usage_pattern(self):
        """사용 패턴 분석"""
        if not PANDAS_AVAILABLE:
            return "pandas가 설치되지 않아 분석을 수행할 수 없습니다."
            
        df = self.get_usage_stats(days=7)
        
        if df.empty:
            return "분석할 데이터가 없습니다."
            
        # 기본 통계
        total_hours = df['total_duration'].sum() / 3600
        daily_avg = total_hours / 7
        unique_apps = df['app_name'].nunique()
        
        # 앱별 사용시간 분석
        app_usage = df.groupby('app_name')['total_duration'].sum().sort_values(ascending=False)
        top_app = app_usage.index[0]
        top_app_hours = app_usage.iloc[0] / 3600
        
        # 상위 5개 앱
        top_5_apps = app_usage.head(5)
        top_5_text = "\n".join([f"  {i+1}. {app}: {hours/3600:.1f}시간" for i, (app, hours) in enumerate(top_5_apps.items())])
        
        # 일별 사용시간 분석
        daily_usage = df.groupby('date')['total_duration'].sum() / 3600
        max_day = daily_usage.idxmax()
        max_day_hours = daily_usage.max()
        min_day = daily_usage.idxmin()
        min_day_hours = daily_usage.min()
        
        # 사용 패턴 분석
        productivity_apps = ['chrome', 'firefox', 'edge', 'notepad', 'code', 'visual studio', 'pycharm', 'word', 'excel', 'powerpoint']
        entertainment_apps = ['steam', 'discord', 'spotify', 'youtube', 'netflix', 'game', 'minecraft', 'league']
        
        productivity_time = 0
        entertainment_time = 0
        
        for app, duration in app_usage.items():
            app_lower = app.lower()
            if any(prod in app_lower for prod in productivity_apps):
                productivity_time += duration
            elif any(ent in app_lower for ent in entertainment_apps):
                entertainment_time += duration
        
        productivity_hours = productivity_time / 3600
        entertainment_hours = entertainment_time / 3600
        
        # 집중도 분석 (상위 앱이 전체 사용시간에서 차지하는 비율)
        concentration_ratio = (top_5_apps.sum() / app_usage.sum()) * 100
        
        analysis = f"""
📊 지난 7일간 상세 컴퓨터 사용 분석

🕐 기본 통계:
  • 총 사용시간: {total_hours:.1f}시간
  • 일평균 사용시간: {daily_avg:.1f}시간
  • 사용한 앱 수: {unique_apps}개

🏆 앱별 사용시간 (상위 5개):
{top_5_text}

📅 일별 사용 패턴:
  • 가장 많이 사용한 날: {max_day} ({max_day_hours:.1f}시간)
  • 가장 적게 사용한 날: {min_day} ({min_day_hours:.1f}시간)
  • 일일 사용시간 편차: {daily_usage.std():.1f}시간

🎯 사용 목적별 분석:
  • 업무/생산성: {productivity_hours:.1f}시간 ({productivity_hours/total_hours*100:.1f}%)
  • 엔터테인먼트: {entertainment_hours:.1f}시간 ({entertainment_hours/total_hours*100:.1f}%)

📈 집중도 분석:
  • 상위 5개 앱 집중도: {concentration_ratio:.1f}%
  • 앱 사용 다양성: {'높음' if unique_apps > 20 else '보통' if unique_apps > 10 else '낮음'}

💡 인사이트:
"""
        
        # 인사이트 추가
        if daily_avg > 8:
            analysis += "• 컴퓨터 사용시간이 많은 편입니다. 휴식을 잊지 마세요.\n"
        elif daily_avg > 4:
            analysis += "• 적당한 컴퓨터 사용시간을 보이고 있습니다.\n"
        else:
            analysis += "• 컴퓨터 사용시간이 적은 편입니다.\n"
            
        if concentration_ratio > 70:
            analysis += "• 특정 앱에 집중하는 경향이 강합니다.\n"
        elif concentration_ratio > 50:
            analysis += "• 적당한 앱 사용 집중도를 보입니다.\n"
        else:
            analysis += "• 다양한 앱을 골고루 사용합니다.\n"
            
        if productivity_hours > entertainment_hours:
            analysis += "• 생산성 앱 사용이 엔터테인먼트보다 많습니다.\n"
        elif entertainment_hours > productivity_hours:
            analysis += "• 엔터테인먼트 앱 사용이 생산성보다 많습니다.\n"
        else:
            analysis += "• 생산성과 엔터테인먼트 사용이 균형적입니다.\n"
            
        return analysis
    
    def get_realtime_stats(self):
        """실시간 통계 정보"""
        if not PANDAS_AVAILABLE:
            return "pandas가 설치되지 않아 실시간 통계를 가져올 수 없습니다."
            
        # 오늘 하루 통계
        today_df = self.get_usage_stats(days=1)
        
        if today_df.empty:
            return "오늘 사용 데이터가 없습니다."
            
        # 오늘 총 사용시간
        today_total = today_df['total_duration'].sum() / 3600
        
        # 오늘 가장 많이 사용한 앱
        today_apps = today_df.groupby('app_name')['total_duration'].sum().sort_values(ascending=False)
        top_today_app = today_apps.index[0] if not today_apps.empty else "없음"
        top_today_hours = today_apps.iloc[0] / 3600 if not today_apps.empty else 0
        
        # 현재 시간 기준 사용률
        current_hour = datetime.now().hour
        if current_hour < 6:
            time_period = "새벽"
        elif current_hour < 12:
            time_period = "오전"
        elif current_hour < 18:
            time_period = "오후"
        else:
            time_period = "저녁"
            
        # 주간 비교
        weekly_df = self.get_usage_stats(days=7)
        if not weekly_df.empty:
            weekly_avg = weekly_df['total_duration'].sum() / (3600 * 7)
            today_vs_weekly = ((today_total - weekly_avg) / weekly_avg * 100) if weekly_avg > 0 else 0
        else:
            today_vs_weekly = 0
            
        stats = f"""
📱 실시간 사용 통계

🕐 오늘 하루:
  • 총 사용시간: {today_total:.1f}시간
  • 가장 많이 사용한 앱: {top_today_app} ({top_today_hours:.1f}시간)
  • 사용한 앱 수: {today_df['app_name'].nunique()}개
  • 현재 시간대: {time_period} ({current_hour}시)

📊 주간 대비:
  • 일평균 대비: {today_vs_weekly:+.1f}%
  • {'평소보다 많이 사용 중' if today_vs_weekly > 10 else '평소보다 적게 사용 중' if today_vs_weekly < -10 else '평소와 비슷한 사용량'}

⏰ 현재 추적 중인 앱: {self.current_app if self.current_app else '없음'}
"""
        return stats

def main():
    tracker = AppUsageTracker()
    
    # 추적 시작 (별도 스레드에서)
    tracking_thread = threading.Thread(target=tracker.track_usage)
    tracking_thread.daemon = True
    tracking_thread.start()
    
    print("앱 사용시간 추적이 시작되었습니다.")
    print("종료하려면 Ctrl+C를 누르세요.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n추적을 종료합니다...")
        tracker.stop_tracking()

if __name__ == "__main__":
    main()
