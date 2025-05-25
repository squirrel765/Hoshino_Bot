# weather.py
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv() # .env 파일에서 환경 변수 로드
API_KEY = os.getenv('API_KEY')  # OpenWeatherMap API Key
BASE_URL = 'https://api.openweathermap.org/data/2.5/forecast'

city_map = {
    "서울": "Seoul",
    "부산": "Busan",
    "인천": "Incheon",
    "대구": "Daegu",
    "광주": "Gwangju",
    "대전": "Daejeon",
    "울산": "Ulsan",
    "수원": "Suwon",
    "제주": "Jeju",
    "파주": "Paju",
    "평양": "Pyongyang",
    "도쿄": "Tokyo",
    # 필요한 도시를 계속 추가할 수 있어요
}

def forecast_today(city_kr: str) -> str:
    if not API_KEY:
        print("OpenWeatherMap API_KEY가 .env 파일에 설정되지 않았습니다.")
        return "이런, 날씨 정보를 가져오기 위한 중요한 설정이 빠진 것 같아. 관리자에게 슬쩍 알려줘, 선생."

    city_en = city_map.get(city_kr)
    if not city_en:
        # 이 경우는 보통 generate_response에서 처리되지만, 만약을 위해 남겨둡니다.
        return f"음... {city_kr}는 아직 지도에 없는 도시인가봐. 내가 아는 도시인지 다시 한번 확인해줄래?"

    params = {
        'q': city_en,
        'appid': API_KEY,
        'units': 'metric', # 섭씨 온도
        'lang': 'kr'      # 한국어 설명
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10) # 타임아웃 설정
        response.raise_for_status()  # 200 OK가 아니면 HTTPError 발생
        data = response.json()

        if data.get("cod") != "200":
            error_message = data.get("message", "알 수 없는 API 오류")
            print(f"날씨 API 응답 오류 (도시: {city_en}, 코드: {data.get('cod')}): {error_message}")
            return f"'{city_kr}' 날씨 정보를 가져오는데 실패했어. 도시 이름이 정확한지 확인하거나, 나중에 다시 시도해줘. (서버 메시지: {error_message})"

        today = datetime.now().date()
        temps = []
        descriptions = []
        found_today_data = False

        for entry in data.get('list', []):
            dt_object = datetime.fromtimestamp(entry['dt'])
            if dt_object.date() == today:
                found_today_data = True
                temps.append(entry['main']['temp'])
                if entry.get('weather') and len(entry['weather']) > 0:
                    descriptions.append(entry['weather'][0]['description'])

        if not found_today_data:
            print(f"오늘({today}) {city_kr}({city_en})에 대한 예보 데이터가 API 응답에 없습니다.")
            return f"흠… 오늘 {city_kr} 날씨 정보를 찾을 수가 없었어. 혹시 너무 이른 시간이거나 늦은 시간일까? 내일 다시 확인해볼게!"

        if temps:
            min_temp = min(temps)
            max_temp = max(temps)
            if descriptions:
                # 가장 자주 등장하는 날씨 설명을 대표로 사용
                main_desc = max(set(descriptions), key=descriptions.count)
            else:
                main_desc = "날씨 정보 없음" # 드문 경우
            return f"선생, 오늘 {city_kr}은(는) {main_desc}이(가) 예상된대. 기온은 최저 {min_temp:.1f}도에서 최고 {max_temp:.1f}도 사이니까 옷차림에 참고하라구~ ☁️🌂"
        else:
            # found_today_data는 True인데 temps가 비어있는 경우 (데이터 구조 문제)
            print(f"오늘({today}) {city_kr}({city_en}) 날씨 데이터는 있었으나 온도 정보를 추출하지 못했습니다.")
            return f"이상하다... 오늘 {city_kr} 날씨 정보는 있는데, 자세한 내용을 모르겠어. 잠시 후에 다시 물어봐줄래?"

    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code
        print(f"날씨 API HTTP 오류 (도시: {city_en}, 상태 코드: {status_code}): {http_err}")
        if status_code == 401:
            return "이런, 날씨 정보를 가져올 권한이 없나 봐. API 키가 문제일지도? 관리자에게 알려줘야겠어."
        elif status_code == 404:
            return f"음... '{city_kr}'({city_en})라는 도시를 찾을 수 없다고 나와. 도시 이름이 정확한지 다시 한번 확인해줄래?"
        return f"우웅… {city_kr} 날씨 정보를 가져오는 중 네트워크 문제가 생겼나봐 (오류 코드: {status_code}). 조금 있다가 다시 시도해줄래, 선생?"
    except requests.exceptions.Timeout:
        print(f"날씨 API 요청 시간 초과 (도시: {city_en})")
        return f"끙... {city_kr} 날씨 정보를 가져오는데 너무 오래 걸리네. 서버가 느린가? 잠시 후에 다시 물어봐줘."
    except requests.exceptions.RequestException as req_err:
        print(f"날씨 API 요청 오류 (도시: {city_en}): {req_err}")
        return f"우웅… {city_kr} 날씨 정보를 요청하는 데 문제가 생겼어. 인터넷 연결을 확인하고 다시 시도해줄래?"
    except KeyError as key_err:
        print(f"날씨 API 응답 데이터 형식 오류 (도시: {city_en}): {key_err}")
        return f"날씨 정보를 받았는데... 내가 모르는 말로 되어있네. {city_kr} 날씨는 나중에 다시 알려줄게, 선생."
    except Exception as e:
        print(f"날씨 API 처리 중 알 수 없는 오류 (도시: {city_en}): {e}")
        return "우웅… 날씨 정보를 가져오는 데 예상치 못한 문제가 생겼어. 조금 있다가 다시 시도해줄래, 선생?"