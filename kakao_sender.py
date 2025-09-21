"""
카카오톡 메시지 전송 모듈
- 카카오톡 API를 통한 메시지 전송
- 이미지 첨부 기능
- 자동화 스케줄링
"""

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("경고: requests 모듈이 설치되지 않았습니다. 카카오톡 기능을 사용하려면 'pip install requests'를 실행하세요.")

import json
import os
from datetime import datetime
import base64
import http.server
import socketserver
import threading
import webbrowser
from urllib.parse import urlparse, parse_qs

class KakaoCallbackHandler(http.server.BaseHTTPRequestHandler):
    """카카오 API 인증 콜백을 처리하는 HTTP 서버 핸들러"""
    
    def do_GET(self):
        """GET 요청 처리"""
        if self.path.startswith('/callback'):
            # URL에서 code 파라미터 추출
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            if 'code' in query_params:
                code = query_params['code'][0]
                # 전역 변수에 코드 저장
                KakaoCallbackHandler.auth_code = code
                
                # 성공 응답
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                
                response = """
                <html>
                <head>
                    <title>인증 완료</title>
                    <meta charset="utf-8">
                </head>
                <body>
                    <h1>✅ 카카오톡 인증이 완료되었습니다!</h1>
                    <p>이 창을 닫고 터미널로 돌아가세요.</p>
                </body>
                </html>
                """
                self.wfile.write(response.encode('utf-8'))
            else:
                # 오류 응답
                self.send_response(400)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                
                response = """
                <html>
                <head>
                    <title>인증 실패</title>
                    <meta charset="utf-8">
                </head>
                <body>
                    <h1>❌ 인증에 실패했습니다.</h1>
                    <p>다시 시도해주세요.</p>
                </body>
                </html>
                """
                self.wfile.write(response.encode('utf-8'))
        else:
            # 다른 경로는 404
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """로그 메시지 비활성화"""
        pass

class KakaoSender:
    def __init__(self, config_file="kakao_config.json"):
        if not REQUESTS_AVAILABLE:
            print("오류: requests 모듈이 필요합니다. 'pip install requests'를 실행하세요.")
            return
        self.config_file = config_file
        self.config = self.load_config()
        
    def load_config(self):
        """카카오톡 API 설정 로드"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 기본 설정 파일 생성
            default_config = {
                "app_key": "",
                "redirect_uri": "http://localhost:8080/callback",
                "access_token": "",
                "refresh_token": "",
                "friend_uuid": ""  # 나에게 보내기의 경우 빈 문자열
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            return default_config
            
    def save_config(self):
        """설정 저장"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
            
    def get_authorization_url(self):
        """카카오톡 인증 URL 생성"""
        base_url = "https://kauth.kakao.com/oauth/authorize"
        params = {
            "client_id": self.config["app_key"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": "talk_message"
        }
        
        url = base_url + "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return url
        
    def get_access_token(self, authorization_code):
        """인증 코드로 액세스 토큰 획득"""
        url = "https://kauth.kakao.com/oauth/token"
        
        data = {
            "grant_type": "authorization_code",
            "client_id": self.config["app_key"],
            "redirect_uri": self.config["redirect_uri"],
            "code": authorization_code
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            self.config["access_token"] = token_data["access_token"]
            self.config["refresh_token"] = token_data.get("refresh_token", "")
            self.save_config()
            return True
        else:
            print(f"토큰 획득 실패: {response.text}")
            return False
            
    def refresh_access_token(self):
        """액세스 토큰 갱신"""
        if not self.config["refresh_token"]:
            return False
            
        url = "https://kauth.kakao.com/oauth/token"
        
        data = {
            "grant_type": "refresh_token",
            "client_id": self.config["app_key"],
            "refresh_token": self.config["refresh_token"]
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            self.config["access_token"] = token_data["access_token"]
            if "refresh_token" in token_data:
                self.config["refresh_token"] = token_data["refresh_token"]
            self.save_config()
            return True
        else:
            print(f"토큰 갱신 실패: {response.text}")
            return False
            
    def send_text_message(self, message):
        """텍스트 메시지 전송"""
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        
        headers = {
            "Authorization": f"Bearer {self.config['access_token']}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        template_object = {
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": "https://developers.kakao.com",
                "mobile_web_url": "https://developers.kakao.com"
            }
        }
        
        data = {
            "template_object": json.dumps(template_object, ensure_ascii=False)
        }
        
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            print("메시지 전송 성공")
            return True
        elif response.status_code == 401:
            # 토큰 만료 시 갱신 시도
            if self.refresh_access_token():
                return self.send_text_message(message)
            else:
                print("토큰 갱신 실패")
                return False
        else:
            print(f"메시지 전송 실패: {response.text}")
            return False
            
    def send_image_message(self, image_path, message=""):
        """이미지 메시지 전송"""
        # 먼저 이미지 업로드
        upload_url = "https://kapi.kakao.com/v2/api/talk/memo/scrap/send"
        
        headers = {
            "Authorization": f"Bearer {self.config['access_token']}"
        }
        
        # 이미지를 base64로 인코딩
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
            
        # 스크랩 형태로 전송
        template_object = {
            "object_type": "feed",
            "content": {
                "title": "앱 사용시간 통계",
                "description": message,
                "image_url": f"data:image/png;base64,{image_data}",
                "link": {
                    "web_url": "https://developers.kakao.com",
                    "mobile_web_url": "https://developers.kakao.com"
                }
            }
        }
        
        data = {
            "template_object": json.dumps(template_object, ensure_ascii=False)
        }
        
        response = requests.post(upload_url, headers=headers, data=data)
        
        if response.status_code == 200:
            print("이미지 메시지 전송 성공")
            return True
        elif response.status_code == 401:
            if self.refresh_access_token():
                return self.send_image_message(image_path, message)
            else:
                print("토큰 갱신 실패")
                return False
        else:
            print(f"이미지 메시지 전송 실패: {response.text}")
            return False
            
    def send_multiple_images(self, image_paths, message=""):
        """여러 이미지를 순차적으로 전송"""
        success_count = 0
        
        # 먼저 텍스트 메시지 전송
        if message:
            if self.send_text_message(message):
                success_count += 1
                
        # 각 이미지를 개별적으로 전송
        for i, image_path in enumerate(image_paths):
            if os.path.exists(image_path):
                chart_name = os.path.basename(image_path).replace('.png', '')
                chart_message = f"📊 {chart_name} 차트"
                
                if self.send_image_message(image_path, chart_message):
                    success_count += 1
                    
        return success_count > 0
        
    def start_callback_server(self, port=8080):
        """카카오 API 인증을 위한 콜백 서버 시작"""
        try:
            # 서버 생성
            httpd = socketserver.TCPServer(("localhost", port), KakaoCallbackHandler)
            print(f"인증 서버가 localhost:{port}에서 시작되었습니다.")
            
            # 서버를 별도 스레드에서 실행
            def run_server():
                try:
                    httpd.serve_forever()
                except Exception as e:
                    print(f"서버 실행 중 오류: {e}")
            
            server_thread = threading.Thread(target=run_server)
            server_thread.daemon = True
            server_thread.start()
            
            # 서버가 시작될 때까지 잠시 대기
            import time
            time.sleep(0.5)
            
            return httpd
        except OSError as e:
            if e.errno == 10048:  # 포트가 이미 사용 중
                print(f"포트 {port}가 이미 사용 중입니다. 다른 포트를 시도합니다.")
                return self.start_callback_server(port + 1)
            else:
                print(f"서버 시작 오류: {e}")
                return None

    def setup_kakao_api(self):
        """카카오톡 API 초기 설정 가이드"""
        print("=== 카카오톡 API 설정 가이드 ===")
        print("1. https://developers.kakao.com 에서 앱을 생성하세요.")
        print("2. 플랫폼 설정에서 Web 플랫폼을 추가하고 도메인을 등록하세요.")
        print("3. 제품 설정에서 '카카오톡 메시지'를 활성화하세요.")
        print("4. 앱 키(REST API 키)를 복사하세요.")
        print()
        
        app_key = input("앱 키(REST API 키)를 입력하세요: ").strip()
        if app_key:
            self.config["app_key"] = app_key
            self.save_config()
            
            # 콜백 서버 시작
            print("\n인증 서버를 시작합니다...")
            server = self.start_callback_server()
            if not server:
                print("서버 시작에 실패했습니다.")
                return False
            
            # 인증 URL 생성 및 브라우저 열기
            auth_url = self.get_authorization_url()
            print(f"\n인증 URL: {auth_url}")
            print("브라우저가 자동으로 열립니다...")
            
            try:
                webbrowser.open(auth_url)
            except Exception as e:
                print(f"브라우저 열기 실패: {e}")
                print("위 URL을 수동으로 브라우저에서 열어주세요.")
            
            # 인증 코드 대기
            print("\n카카오톡 인증을 완료해주세요...")
            print("인증이 완료되면 자동으로 진행됩니다.")
            
            # 인증 코드 대기 (최대 5분)
            import time
            timeout = 300  # 5분
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if hasattr(KakaoCallbackHandler, 'auth_code') and KakaoCallbackHandler.auth_code:
                    auth_code = KakaoCallbackHandler.auth_code
                    print(f"인증 코드를 받았습니다: {auth_code[:10]}...")
                    
                    if self.get_access_token(auth_code):
                        print("✅ 카카오톡 API 설정이 완료되었습니다!")
                        return True
                    else:
                        print("❌ 인증 실패")
                        return False
                
                time.sleep(1)
            
            print("⏰ 인증 시간이 초과되었습니다.")
            return False
        
        return False

def test_kakao_sender():
    """카카오 전송 테스트"""
    if not REQUESTS_AVAILABLE:
        print("requests 모듈이 설치되지 않아 카카오톡 기능을 사용할 수 없습니다.")
        print("다음 명령어로 requests를 설치하세요: pip install requests")
        return
        
    sender = KakaoSender()
    
    # 설정이 없으면 초기 설정 진행
    if not sender.config.get("access_token"):
        if not sender.setup_kakao_api():
            print("카카오톡 API 설정을 완료해주세요.")
            return
            
    # 테스트 메시지 전송
    test_message = "📱 앱 사용시간 추적 프로그램 테스트 메시지입니다!"
    if sender.send_text_message(test_message):
        print("테스트 메시지 전송 성공!")
    else:
        print("테스트 메시지 전송 실패")

def test_with_code(auth_code):
    """인증 코드로 직접 테스트"""
    if not REQUESTS_AVAILABLE:
        print("requests 모듈이 설치되지 않아 카카오톡 기능을 사용할 수 없습니다.")
        return
        
    sender = KakaoSender()
    
    print(f"인증 코드로 토큰을 받는 중...: {auth_code[:10]}...")
    
    if sender.get_access_token(auth_code):
        print("✅ 카카오톡 API 설정이 완료되었습니다!")
        
        # 테스트 메시지 전송
        test_message = "📱 앱 사용시간 추적 프로그램 테스트 메시지입니다!"
        if sender.send_text_message(test_message):
            print("테스트 메시지 전송 성공!")
        else:
            print("테스트 메시지 전송 실패")
    else:
        print("❌ 인증 실패")

if __name__ == "__main__":
    test_kakao_sender()
