"""
자동화 스케줄러 모듈
- 주간 리포트 자동 생성 및 전송
- 백그라운드 실행
- 시스템 트레이 지원
"""

import schedule
import time
import threading
import os
import sys
from datetime import datetime, timedelta
import logging

# GUI 라이브러리 (시스템 트레이용)
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("시스템 트레이 기능을 사용하려면 'pip install pystray pillow'를 실행하세요.")

from main import AppUsageTracker
from kakao_sender import KakaoSender

class UsageScheduler:
    def __init__(self):
        self.tracker = AppUsageTracker()
        self.kakao_sender = KakaoSender()
        self.running = False
        self.tracking_thread = None
        self.scheduler_thread = None
        self.tray_icon = None
        
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('app_usage_scheduler.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def create_tray_icon(self):
        """시스템 트레이 아이콘 생성"""
        if not TRAY_AVAILABLE:
            return None
            
        # 간단한 아이콘 이미지 생성
        image = Image.new('RGB', (64, 64), color='blue')
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill='white')
        draw.text((20, 25), "AU", fill='blue')
        
        menu = pystray.Menu(
            pystray.MenuItem("상태 확인", self.show_status),
            pystray.MenuItem("즉시 리포트 전송", self.send_immediate_report),
            pystray.MenuItem("카카오톡 설정", self.setup_kakao),
            pystray.MenuItem("종료", self.quit_application)
        )
        
        return pystray.Icon("AppUsageTracker", image, "앱 사용시간 추적기", menu)
        
    def show_status(self, icon=None, item=None):
        """현재 상태 표시"""
        try:
            df = self.tracker.get_usage_stats(days=1)
            if not df.empty:
                total_time = df['total_duration'].sum() / 3600
                app_count = df['app_name'].nunique()
                message = f"오늘 사용시간: {total_time:.1f}시간\n사용 앱 수: {app_count}개"
            else:
                message = "오늘 사용 데이터가 없습니다."
                
            self.logger.info(f"상태 확인: {message}")
            
            # Windows 알림 (선택사항)
            try:
                import win10toast
                toaster = win10toast.ToastNotifier()
                toaster.show_toast("앱 사용시간 추적기", message, duration=5)
            except ImportError:
                print(message)
                
        except Exception as e:
            self.logger.error(f"상태 확인 중 오류: {e}")
            
    def setup_kakao(self, icon=None, item=None):
        """카카오톡 설정"""
        self.logger.info("카카오톡 설정 시작")
        self.kakao_sender.setup_kakao_api()
        
    def send_immediate_report(self, icon=None, item=None):
        """즉시 리포트 전송"""
        self.logger.info("즉시 리포트 전송 시작")
        self.send_weekly_report()
        
    def quit_application(self, icon=None, item=None):
        """애플리케이션 종료"""
        self.logger.info("애플리케이션 종료")
        self.stop()
        if self.tray_icon:
            self.tray_icon.stop()
            
    def generate_weekly_report(self):
        """주간 리포트 생성"""
        try:
            self.logger.info("주간 리포트 생성 시작")
            
            # 차트 생성
            charts = []
            chart_files = [
                ("daily_usage.png", self.tracker.create_daily_chart),
                ("weekly_usage.png", self.tracker.create_weekly_chart),
                ("monthly_usage.png", self.tracker.create_monthly_chart),
                ("app_usage.png", self.tracker.create_app_usage_chart)
            ]
            
            for filename, chart_func in chart_files:
                try:
                    chart_path = chart_func(filename)
                    if chart_path and os.path.exists(chart_path):
                        charts.append(chart_path)
                        self.logger.info(f"차트 생성 완료: {filename}")
                except Exception as e:
                    self.logger.error(f"차트 생성 실패 {filename}: {e}")
                    
            # 사용 패턴 분석
            analysis = self.tracker.analyze_usage_pattern()
            
            return charts, analysis
            
        except Exception as e:
            self.logger.error(f"주간 리포트 생성 중 오류: {e}")
            return [], "리포트 생성 중 오류가 발생했습니다."
            
    def send_weekly_report(self):
        """주간 리포트 카카오톡 전송"""
        try:
            self.logger.info("주간 리포트 전송 시작")
            
            # 카카오톡 설정 확인
            if not self.kakao_sender.config.get("access_token"):
                self.logger.warning("카카오톡 API가 설정되지 않았습니다.")
                return False
                
            # 리포트 생성
            charts, analysis = self.generate_weekly_report()
            
            # 메시지 전송
            current_time = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
            header_message = f"📊 주간 앱 사용시간 리포트\n생성일시: {current_time}\n\n{analysis}"
            
            if charts:
                success = self.kakao_sender.send_multiple_images(charts, header_message)
                if success:
                    self.logger.info("주간 리포트 전송 완료")
                    return True
                else:
                    self.logger.error("주간 리포트 전송 실패")
                    return False
            else:
                # 차트가 없으면 텍스트만 전송
                success = self.kakao_sender.send_text_message(header_message)
                if success:
                    self.logger.info("주간 리포트 (텍스트만) 전송 완료")
                    return True
                else:
                    self.logger.error("주간 리포트 전송 실패")
                    return False
                    
        except Exception as e:
            self.logger.error(f"주간 리포트 전송 중 오류: {e}")
            return False
            
    def schedule_jobs(self):
        """작업 스케줄링 설정"""
        # 매주 일요일 오후 10시에 리포트 전송
        schedule.every().sunday.at("22:00").do(self.send_weekly_report)
        
        # 테스트용: 매일 오후 6시에 리포트 전송 (필요시 활성화)
        # schedule.every().day.at("18:00").do(self.send_weekly_report)
        
        self.logger.info("스케줄 설정 완료: 매주 일요일 오후 10시")
        
    def run_scheduler(self):
        """스케줄러 실행"""
        self.logger.info("스케줄러 시작")
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
            
    def start(self):
        """추적 및 스케줄러 시작"""
        if self.running:
            return
            
        self.running = True
        self.logger.info("앱 사용시간 추적 및 스케줄러 시작")
        
        # 스케줄 설정
        self.schedule_jobs()
        
        # 앱 사용시간 추적 스레드 시작
        self.tracking_thread = threading.Thread(target=self.tracker.track_usage)
        self.tracking_thread.daemon = True
        self.tracking_thread.start()
        
        # 스케줄러 스레드 시작
        self.scheduler_thread = threading.Thread(target=self.run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # 시스템 트레이 실행
        if TRAY_AVAILABLE:
            self.tray_icon = self.create_tray_icon()
            if self.tray_icon:
                self.logger.info("시스템 트레이 아이콘 생성")
                self.tray_icon.run()
        else:
            # 트레이가 없으면 콘솔에서 대기
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
                
    def stop(self):
        """추적 및 스케줄러 중지"""
        if not self.running:
            return
            
        self.logger.info("앱 사용시간 추적 및 스케줄러 중지")
        self.running = False
        self.tracker.stop_tracking()
        
        # 스레드 종료 대기
        if self.tracking_thread and self.tracking_thread.is_alive():
            self.tracking_thread.join(timeout=5)
            
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

def main():
    """메인 실행 함수"""
    scheduler = UsageScheduler()
    
    print("=== 앱 사용시간 추적 및 자동화 프로그램 ===")
    print("1. 앱 사용시간을 자동으로 추적합니다.")
    print("2. 매주 일요일 오후 10시에 카카오톡으로 리포트를 전송합니다.")
    print("3. 시스템 트레이에서 상태를 확인할 수 있습니다.")
    print()
    
    # 카카오톡 설정 확인
    if not scheduler.kakao_sender.config.get("access_token"):
        print("카카오톡 API 설정이 필요합니다.")
        setup_choice = input("지금 설정하시겠습니까? (y/n): ").lower()
        if setup_choice == 'y':
            scheduler.kakao_sender.setup_kakao_api()
        else:
            print("나중에 시스템 트레이에서 설정할 수 있습니다.")
    
    print("\n프로그램을 시작합니다...")
    print("시스템 트레이에서 상태를 확인하고 설정을 변경할 수 있습니다.")
    print("종료하려면 시스템 트레이 아이콘을 우클릭하여 '종료'를 선택하세요.")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다...")
        scheduler.stop()

if __name__ == "__main__":
    main()
