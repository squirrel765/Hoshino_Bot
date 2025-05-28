# Hoshino Bot (호시노 봇)

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![Discord.py](https://img.shields.io/badge/discord.py-2.x-7289DA.svg)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<!-- 필요하다면 다른 뱃지 추가 (예: 빌드 상태, 코드 커버리지 등) -->

으헤~ 선생, 내 프로젝트에 와줘서 고마워! 이 봇은 다양한 재미있는 기능을 제공하는 디스코드 봇이야.

## 🌟 주요 기능

*   **AI 채팅**: Google Gemini AI 모델을 사용하여 자연스러운 대화가 가능해. 나한테 말을 걸어봐, 선생!
*   **날씨 정보**: 특정 도시의 현재 날씨를 알려줄 수 있어. (예: `서울 날씨`)
*   **랜덤 이미지**: 내가 가진 그림 중에 하나를 랜덤으로 보여줄게! (`!사진`)
*   **가위바위보**: 나와 가위바위보 한 판 어때? 버튼으로 선택해봐! (`!가위바위보`)
*   **주사위 굴리기**: 다양한 면체의 주사위를 굴릴 수 있어. (`!주사위`, `!주사위 2d20`)
*   **사다리 타기**: 참가자와 결과를 입력하면 공평하게 사다리를 타줄게! (`!사다리 참가자1 참가자2 -> 결과1 결과2`)
*   **반응 GIF**: 다른 선생에게 재미있는 반응 GIF를 보낼 수 있어! (`!ok @멘션`, `!hug @멘션` 등 `reaction_gifs` 폴더 내용에 따라 자동 생성)
*   **대화 초기화**: 나와의 대화 기록을 잊어버리게 할 수 있어. (`!초기화`)
*   **로그 확인 (관리자용)**: 봇 관리자는 최근 활동 로그를 확인할 수 있어. (`!로그`)

## 🛠️ 설치 및 실행 방법

### 사전 준비물

*   Python 3.8 이상
*   Git
*   `pip` (Python 패키지 관리자)
*   `venv` (Python 가상 환경 도구)
*   `tmux` (권장, 백그라운드 실행용)

### 설치 과정 (Linux/Ubuntu 기준)

1.  **시스템 패키지 설치**:
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install git python3 python3-pip python3-venv tmux -y
    ```

2.  **프로젝트 클론**:
    ```bash
    git clone https://github.com/squirrel765/Hoshino_Bot.git # 본인의 저장소 주소로 변경
    cd Hoshino_Bot
    ```

3.  **가상 환경 설정 및 라이브러리 설치**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -U pip
    pip install -r requirements.txt
    ```

4.  **환경 변수 설정 (`.env` 파일 생성)**:
    프로젝트 루트 디렉토리(`Hoshino_Bot/`)에 `.env` 파일을 생성하고 다음 내용을 실제 값으로 채워주세요:
    ```env
    DISCORD_TOKEN=여러분의_디스코드_봇_토큰
    GEMINI_API_KEY=여러분의_Gemini_API_키
    ADMIN_USER_ID=관리자로_지정할_디스코드_사용자_ID
    ```

5.  **필수 폴더 및 파일 배치 (필요시)**:
    *   `img/`: `!사진` 명령어 및 `!가위바위보` 명령어에 사용될 이미지/GIF가 들어가는 폴더입니다. (`rock_paper_scissors.gif` 포함)
    *   `reaction_gifs/`: 반응 명령어에 사용될 GIF 파일들이 들어가는 폴더입니다. (예: `OK.gif`, `HUG_1.gif` 등)
    *   만약 이 폴더들이 Git 저장소에 포함되어 있지 않다면, 직접 생성하고 해당 파일들을 넣어주세요.

6.  **봇 실행**:
    ```bash
    # (가상 환경이 활성화된 상태여야 합니다: source venv/bin/activate)
    tmux new -s hoshino # 새 tmux 세션 생성 (이름은 원하는대로)
    # tmux 세션 내에서:
    # cd /path/to/Hoshino_Bot # 만약 경로가 다르다면 이동
    # source venv/bin/activate # tmux 세션 내에서 다시 활성화 필요할 수 있음
    python3 bot.py # 또는 실제 봇 실행 파일명
    ```
    Tmux 세션에서 빠져나오려면 `Ctrl+b` 후 `d`를 누릅니다. 봇은 백그라운드에서 계속 실행됩니다.
    다시 접속하려면 `tmux attach -t hoshino`를 입력하세요.

## ⚙️ 설정

*   **봇 접두사(Prefix)**: 현재 `!`로 설정되어 있습니다. (`bot.py` 파일에서 변경 가능)
*   **반응 GIF 추가**: `reaction_gifs/` 폴더에 원하는 GIF 파일을 추가하면, 파일 이름(확장자 제외, `_` 앞부분)을 따서 자동으로 명령어가 생성됩니다. (예: `SLEEP_CAT.gif` 추가 시 `!sleep` 명령어로 사용 가능) 파일명은 대문자를 권장합니다 (예: `GOOD.gif`).

## 📝 명령어 목록

봇 내에서 `!도움` 명령어를 입력하면 사용 가능한 모든 명령어와 설명을 볼 수 있어, 선생!

## 🤝 기여 방법

으헤~ 아직은 아저씨 혼자 만들고 있지만, 혹시 도와주고 싶다면 언제든 환영이야!
버그를 발견하거나 새로운 기능 아이디어가 있다면 Issues 탭에 자유롭게 남겨줘.
Pull Request도 환영이야!

## 📄 라이선스

이 프로젝트는 [MIT 라이선스](LICENSE)를 따르고 있어. 자유롭게 사용해도 괜찮아, 선생.

---

만든 사람: [squirrel765](https://github.com/squirrel765) (또는 본인 닉네임/깃허브 프로필 링크)

후훗, 이 봇과 함께 즐거운 시간 보내길 바랄게!