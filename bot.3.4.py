# bot.py (또는 main.py)

import os
import discord
from discord.ext import commands
from discord.ui import View, Button, button # UI 요소 임포트
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import re # 정규 표현식 모듈 추가
import random
import logging # 로깅 모듈 임포트
from logging.handlers import RotatingFileHandler # 로그 파일 관리를 위해 임포트

# 로컬 모듈 임포트
from prompt import SYSTEM_PROMPT
from weather import forecast_today, city_map
from reaction import send_reaction_gif # reaction.py에서 함수 임포트

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
ADMIN_USER_ID_STR = os.getenv('ADMIN_USER_ID') # 관리자 ID 로드

# --- 로거 설정 ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file_path = "bot_activity.log"

logger = logging.getLogger('HoshinoBot') # 봇 애플리케이션용 로거
logger.setLevel(logging.INFO) # 파일과 콘솔에 기본 INFO 레벨

# 파일 핸들러 (로그 파일 생성 및 관리)
file_handler = RotatingFileHandler(
    filename=log_file_path,
    encoding='utf-8',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3  # 최대 3개 백업 파일 (bot_activity.log, .1, .2, .3)
)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# 콘솔 핸들러 (터미널에 로그 출력)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
# --- 로거 설정 끝 ---


if not DISCORD_TOKEN or not GEMINI_API_KEY:
    logger.critical("DISCORD_TOKEN과 GEMINI_API_KEY를 .env 파일에 반드시 설정하세요!")
    exit(1)

ADMIN_USER_ID = None
if ADMIN_USER_ID_STR:
    try:
        ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
    except ValueError:
        logger.error(f"환경변수 ADMIN_USER_ID ('{ADMIN_USER_ID_STR}')가 올바른 숫자 형식이 아닙니다.")
        ADMIN_USER_ID = None # 오류 시 None으로 설정
else:
    logger.warning("ADMIN_USER_ID가 .env 파일에 설정되지 않았습니다. !로그 기능이 제한될 수 있습니다.")


genai.configure(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True # 멤버 정보를 가져오기 위해 (멘션된 사용자 정보, 반응 명령어)

bot = commands.Bot(command_prefix='!', intents=intents)

generation_config = genai.types.GenerationConfig(
    temperature=0.7,
    top_p=0.9,
    top_k=40,
    max_output_tokens=1000,
)

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

try:
    gemini_model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        system_instruction=SYSTEM_PROMPT,
        generation_config=generation_config,
        safety_settings=safety_settings
    )
    logger.info("Gemini 모델 로드 성공.")
except Exception as e:
    logger.error(f"Gemini 모델 로드 실패: {e}")
    logger.error("Gemini API 키 또는 모델 이름을 확인하세요.")
    exit(1)


IMAGE_DIR_NAME = "img" # 'img' 폴더
REACTION_GIF_DIR = "reaction_gifs" # 반응 GIF 폴더, reaction.py와 일치
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
chat_sessions = {}

def get_or_create_chat_session(user_id: str):
    if user_id not in chat_sessions:
        chat_sessions[user_id] = gemini_model.start_chat(history=[])
        logger.info(f"새로운 채팅 세션을 시작합니다: {user_id}")
    return chat_sessions[user_id]

async def generate_response(user_id: str, user_message: str, message_obj: discord.Message = None):
    """날씨 요청을 우선 처리하고, 그 외에는 Gemini API를 사용하여 응답을 생성합니다."""
    supported_cities_kr = list(city_map.keys())
    if supported_cities_kr: # city_map이 비어있지 않은 경우에만 실행
        cities_pattern_group = "|".join(re.escape(city) for city in supported_cities_kr)
        weather_pattern = re.compile(rf"(?i)(?:\? *)?\b({cities_pattern_group})\b\s*(?:은|는|이|가|의)?\s*날씨")
        match = weather_pattern.search(user_message)

        if match:
            found_city_kr = match.group(1)
            logger.info(f"날씨 요청 감지: '{found_city_kr}' (사용자: {user_id}, 원본 메시지: '{user_message}')")
            forecast_result = forecast_today(found_city_kr)
            return f"{forecast_result}\n{found_city_kr} 날씨 정보였어, 선생."

        elif user_message.strip().lower().startswith("?날씨") and not user_message.startswith(bot.command_prefix):
            default_city = "서울"
            if default_city in city_map:
                logger.info(f"일반 날씨 요청 감지 (?날씨). 기본 도시 '{default_city}'로 조회. (사용자: {user_id}, 원본: '{user_message}')")
                forecast_result = forecast_today(default_city)
                return f"어떤 도시인지 정확히 안 알려줘서 일단 {default_city} 날씨를 가져왔어, 선생.\n{forecast_result}\n다른 도시가 궁금하면 '도시이름 날씨' 또는 `?도시이름 날씨`라고 물어봐."
            else:
                logger.warning(f"경고: 기본 도시 '{default_city}'가 city_map에 없습니다.")
                return "날씨를 알려주고 싶은데, 어떤 도시인지 말해줄래, 선생? 예를 들면 '서울 날씨' 이렇게."

    chat_session = get_or_create_chat_session(user_id)
    try:
        logger.info(f"Gemini에게 전달 (ID: {user_id}): {user_message[:100]}{'...' if len(user_message) > 100 else ''}") # 메시지 일부만 로깅
        gemini_response = await chat_session.send_message_async(user_message)
        return gemini_response.text
    except Exception as e:
        logger.error(f"Gemini API 호출 중 오류 발생 (사용자 ID: {user_id}): {e}")
        error_str = str(e).lower()
        if "context length" in error_str or "token" in error_str or "size of the request" in error_str:
            logger.warning(f"컨텍스트/요청 크기 문제로 {user_id}의 세션을 초기화합니다.")
            if user_id in chat_sessions:
                del chat_sessions[user_id]
            return "으음... 방금 무슨 이야기 하고 있었지? 다시 말해줄래, 선생? 머리가 잠깐 하얘졌어~"
        elif "block" in error_str:
            return "으음... 선생, 그건 좀 대답하기 곤란한 내용인 것 같아. 다른 이야기 하자~"
        return "우웅... 지금은 좀 피곤해서 대답하기 어렵네~ 나중에 다시 물어봐줘, 구만."


# bot.py의 register_reaction_commands 함수 부분

async def register_reaction_commands(bot_instance: commands.Bot):
    """reaction_gifs 폴더를 스캔하여 GIF 파일의 '기본 이름'으로 명령어를 동적 생성 및 등록"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gif_folder_path = os.path.join(script_dir, REACTION_GIF_DIR)
    
    # 기본 반응 이름들을 저장할 Set (중복 방지)
    # 예: SLEEP_1.gif, SLEEP_2.gif -> "SLEEP"만 저장
    base_reaction_names = set()
    created_commands_count = 0

    if not os.path.exists(gif_folder_path) or not os.path.isdir(gif_folder_path):
        logger.warning(f"반응 GIF 폴더 '{gif_folder_path}'를 찾을 수 없습니다. 반응 명령어가 생성되지 않습니다.")
        return

    for filename in os.listdir(gif_folder_path):
        if filename.lower().endswith(".gif"):
            # 파일명에서 '기본 반응 이름' 추출. 예: "SLEEP_1.gif" -> "SLEEP", "PAT.gif" -> "PAT"
            # 보통 '_' 이전 부분을 기본 이름으로 사용하거나, 파일명 전체에서 숫자나 특정 구분자 제거
            base_name_parts = os.path.splitext(filename)[0].split('_')
            # 첫 번째 부분을 기본 이름으로 사용 (대문자로 통일)
            # 만약 파일명이 HUG.gif 라면 base_name_parts[0]는 HUG
            # 만약 파일명이 SLEEP_CAT.gif 라면 base_name_parts[0]는 SLEEP
            # 이 로직은 파일명 규칙에 따라 조정될 수 있습니다.
            # 여기서는 가장 간단하게 '_' 앞부분을 사용하거나, '_'가 없으면 전체 이름을 사용합니다.
            potential_base_name = base_name_parts[0].upper()
            
            # 해당 기본 이름으로 시작하는 GIF 파일이 실제로 존재하는지 한 번 더 확인 (폴더 내 다른 파일과 비교)
            # 이 부분은 send_reaction_gif 함수에서 처리하므로, 여기서는 base_reaction_names에 추가만 해도 됨.
            # send_reaction_gif는 potential_base_name으로 시작하는 모든 .gif를 찾을 것임.
            
            # 생성될 명령어 이름 (소문자)
            command_name_lower = potential_base_name.lower()
            
            # 이미 해당 기본 이름으로 명령어가 생성되었거나, 기존 명령어와 충돌하는지 확인
            if command_name_lower in base_reaction_names or bot_instance.get_command(command_name_lower):
                if command_name_lower not in base_reaction_names: # 기존 명령어와 충돌하는 경우
                    logger.warning(f"반응 명령어 '!{command_name_lower}'는 이미 존재하거나 예약된 이름이어서 건너뜁니다. (파일 그룹 시작: {filename})")
                # 이미 처리된 base_name이므로 건너뜀 (예: SLEEP_1.gif 처리 후 SLEEP_2.gif를 만났을 때 !sleep은 이미 생성됨)
                continue 

            # 동적 명령어 콜백 함수 생성
            # reaction_name_for_send_gif는 클로저를 통해 각 명령어 생성 시점의 potential_base_name (대문자) 값을 가짐
            async def dynamic_reaction_command(ctx, target_user: discord.Member, *, reaction_name_for_send_gif=potential_base_name):
                await send_reaction_gif(ctx, target_user, reaction_name_for_send_gif)

            dynamic_reaction_command.__doc__ = f"으헤~ {potential_base_name} 반응을 보여줄게, 선생! (!{command_name_lower} @멘션)"
            
            cmd = commands.Command(dynamic_reaction_command, name=command_name_lower, help=dynamic_reaction_command.__doc__)
            bot_instance.add_command(cmd)
            
            base_reaction_names.add(command_name_lower) # 처리된 기본 이름(소문자) 추가
            created_commands_count += 1
            logger.info(f"동적 반응 명령어 '!{command_name_lower}'가 생성 및 등록되었습니다. (기준 GIF 그룹 시작: {filename})")
    
    if created_commands_count > 0:
        logger.info(f"총 {created_commands_count}개의 동적 반응 명령어 그룹이 등록되었습니다.")
    else:
        logger.info("등록할 수 있는 새로운 동적 반응 명령어가 없습니다.")


# --- 봇 준비 완료 시 실행될 함수 ---
async def setup_hook():
    logger.info("setup_hook: 봇 준비 시작...")
    await register_reaction_commands(bot) # 봇 인스턴스 전달
    logger.info("setup_hook: 봇 준비 완료 및 명령어 등록 시도 완료.")

bot.setup_hook = setup_hook # setup_hook 함수를 봇에 연결


@bot.event
async def on_ready():
    logger.info(f'봇이 성공적으로 로그인했습니다: {bot.user.name} (ID: {bot.user.id})')
    activity = discord.Game(name="!도움으로 사용법 확인")
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.command(name='초기화')
async def reset_chat_session(ctx: commands.Context):
    user_id = str(ctx.author.id)
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        logger.info(f"사용자 {ctx.author} (ID: {user_id})에 의해 채팅 세션이 초기화되었습니다.")
        await ctx.reply("기존 대화 내용을 잊어버렸어, 선생! 새로운 마음으로 다시 시작하자~ 후후.", mention_author=False)
    else:
        await ctx.reply("응? 아직 우리 대화 시작도 안 한 것 같은데, 선생? 아니면 이미 깨끗한 상태야!", mention_author=False)

@bot.command(name='사진')
async def show_random_image(ctx: commands.Context):
    logger.info(f"!사진 명령어 감지 (사용자: {ctx.author})")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    image_folder_path = os.path.join(script_dir, IMAGE_DIR_NAME)

    if not os.path.exists(image_folder_path) or not os.path.isdir(image_folder_path):
        logger.warning(f"이미지 폴더 '{image_folder_path}'를 찾을 수 없습니다. (!사진)")
        await ctx.reply(f"으음... '{IMAGE_DIR_NAME}' 폴더를 찾을 수 없어, 선생. 이미지를 넣어뒀는지 확인해줄래?", mention_author=False)
        return
    try:
        valid_images = [
            f for f in os.listdir(image_folder_path)
            if os.path.isfile(os.path.join(image_folder_path, f)) and \
            os.path.splitext(f)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
        ]
    except Exception as e:
        logger.error(f"'{image_folder_path}' 폴더에서 이미지 목록을 가져오는 중 오류 발생: {e}")
        await ctx.reply(f"이미지 폴더를 읽는 중에 문제가 생겼어, 선생.", mention_author=False)
        return
    if not valid_images:
        logger.info(f"이미지 폴더 '{image_folder_path}'에 유효한 이미지가 없습니다. (!사진)")
        await ctx.reply(f"'{IMAGE_DIR_NAME}' 폴더에 보여줄 수 있는 이미지가 하나도 없어, 선생. 이미지를 좀 채워줘~", mention_author=False)
        return
    selected_image_name = random.choice(valid_images)
    selected_image_path = os.path.join(image_folder_path, selected_image_name)
    try:
        await ctx.reply(f"으헤~ 내가 가진 그림 중에 하나 골라봤어, 선생!", file=discord.File(selected_image_path), mention_author=False)
        logger.info(f"로컬 이미지 전송: {selected_image_path} (요청자: {ctx.author})")
    except FileNotFoundError:
        logger.error(f"이미지 파일 '{selected_image_path}'를 찾을 수 없습니다. (전송 시도 중)")
        await ctx.reply(f"이미지를 찾았는데... 파일이 갑자기 사라졌나봐, 미안해 선생.", mention_author=False)
    except discord.errors.HTTPException as e:
        if e.status == 413 or (e.text and "Request entity too large" in e.text):
            logger.warning(f"이미지 '{selected_image_path}' 전송 실패: 파일 크기 초과 (8MB).")
            await ctx.reply(f"으... 이 그림은 너무 커서 보여줄 수가 없어, 선생. (8MB 초과)", mention_author=False)
        else:
            logger.error(f"Discord HTTP 에러 (이미지 전송): {e} (파일: {selected_image_path}, 상태: {e.status})")
            await ctx.reply(f"이미지를 보내다가 디스코드에서 문제가 생겼어, 선생... ({e.status})", mention_author=False)
    except Exception as e:
        logger.error(f"로컬 이미지 전송 중 예기치 않은 오류: {e} (파일: {selected_image_path})", exc_info=True)
        await ctx.reply(f"이미지를 보내다가 알 수 없는 문제가 생겼어, 선생...", mention_author=False)


@bot.command(name='도움')
async def show_help(ctx: commands.Context):
    embed = discord.Embed(
        title="📘 호시노 봇 도움말 📘",
        description="으헤~호시노는 이런걸 할줄 안다구 선생!",
        color=discord.Color.from_rgb(173, 216, 230) # Light Blue
    )
    avatar_url = bot.user.display_avatar.url if bot.user else None
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    embed.add_field(name="💬 저와 대화하기", value=f"채널에서 저를 **멘션**(`@{bot.user.name}`)하거나 **DM**으로 메시지를 보내면 대답해드려요!\n예: `@{bot.user.name} 오늘 기분 어때?`\n또는 `?`로 시작하는 질문도 알아들을 수 있어! (예: `?오늘 날씨 어때`)", inline=False)
    embed.add_field(name="☀️ 날씨 물어보기", value="`도시이름 날씨` 또는 `?도시이름 날씨`라고 물어보세요. (예: `서울 날씨`, `?부산 날씨`)\n그냥 `?날씨`라고 물어보면 제가 임의로 서울 날씨를 알려드려요.\n(단, 제가 아는 도시여야 해요!)", inline=False)
    embed.add_field(name="🖼️ 랜덤 그림 보기", value="`!사진` 이라고 입력하면 제가 가진 그림 중 하나를 랜덤으로 보여줄게요!", inline=False)
    embed.add_field(name="🎲 주사위 굴리기", value="`!주사위 [NdM 또는 N]` 형식으로 주사위를 굴릴 수 있어!\n예: `!주사위` (6면체 1개), `!주사위 20` (20면체 1개), `!주사위 2d6` (6면체 2개 합산)", inline=False)
    embed.add_field(name="✂️ 가위바위보", value="`!가위바위보` (또는 `!rps`) 라고 입력하면 나와 가위바위보를 할 수 있어, 선생!\nGIF와 함께 가위, 바위, 보 버튼이 나타나면 하나를 선택해줘!", inline=False)
    embed.add_field(name="🪜 사다리 타기", value="`!사다리 [참가자1] [참가자2] ... -> [결과1] [결과2] ...` 형식으로 사다리 타기를 할 수 있어!\n참가자 수와 결과 수는 같아야 해, 선생.\n예: `!사다리 호시노 시로코 -> 청소하기 낮잠자기`", inline=False)
    
    # 동적으로 생성된 반응 명령어 도움말 추가
    reaction_commands_desc = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gif_folder_path = os.path.join(script_dir, REACTION_GIF_DIR)
    if os.path.exists(gif_folder_path) and os.path.isdir(gif_folder_path):
        for filename in os.listdir(gif_folder_path):
            if filename.lower().endswith(".gif"):
                cmd_name = os.path.splitext(filename)[0].lower()
                if bot.get_command(cmd_name): # 실제로 등록된 명령어만 표시
                     reaction_commands_desc.append(f"`!{cmd_name} @멘션`")
    
    if reaction_commands_desc:
        embed.add_field(name="💞 반응 GIF 보내기", value="다른 선생에게 재미있는 반응을 보여줄 수 있어!\n" + ", ".join(reaction_commands_desc), inline=False)
    else:
        embed.add_field(name="💞 반응 GIF 보내기", value=f"아직 등록된 반응이 없나봐, 선생. (폴더: {REACTION_GIF_DIR})", inline=False)

    embed.add_field(name="🔄 대화 초기화", value="`!초기화` 라고 입력하면 저와의 이전 대화 내용을 잊어버리고 새로 시작할 수 있어요.", inline=False)
    if ADMIN_USER_ID and ctx.author.id == ADMIN_USER_ID: # 관리자에게만 로그 명령어 도움말 표시
        embed.add_field(name="📜 로그 보기 (관리자용)", value="`!로그 [줄 수]` 라고 입력하면 최근 로그를 보여줄게, 선생. 기본 20줄이야.", inline=False)
    embed.add_field(name="🙋 도움말 보기", value="`!도움` 이라고 입력하면 이 도움말을 다시 볼 수 있어요.", inline=False)
    embed.set_footer(text="궁금한 게 있다면 언제든 아저씨에게 물어보라구~.")
    await ctx.reply(embed=embed, mention_author=False)


# --- 가위바위보 기능 (RPSView 클래스 및 명령어) ---
class RPSView(View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30.0) # 30초 후 타임아웃
        self.author_id = author_id
        self.result_message: discord.Message = None # 결과 메시지 (초기 메시지를 수정하기 위함)
        self.user_choice = None
        self.bot_choice = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("으음... 다른 사람의 게임에는 끼어들 수 없어, 선생!", ephemeral=True)
            return False
        return True

    async def process_game(self, interaction: discord.Interaction):
        if self.user_choice is None: # 비정상적인 경우
            logger.warning(f"RPSView.process_game 호출 시 user_choice가 None입니다. (사용자: {interaction.user.id})")
            await interaction.response.send_message("뭔가 잘못된 것 같아, 선생...", ephemeral=True, delete_after=5)
            self.stop()
            return

        choices = ["가위", "바위", "보"]
        self.bot_choice = random.choice(choices)
        result_text = ""
        user_choice_norm = self.user_choice # 버튼 값은 이미 정규화됨
        bot_choice_norm = self.bot_choice

        if user_choice_norm == bot_choice_norm: result_text = "무승부!"
        elif (user_choice_norm == "가위" and bot_choice_norm == "보") or \
             (user_choice_norm == "바위" and bot_choice_norm == "가위") or \
             (user_choice_norm == "보" and bot_choice_norm == "바위"): result_text = "선생의 승리!"
        else: result_text = "나의 승리! 으헤헤~"

        for item in self.children:
            if isinstance(item, Button): item.disabled = True
        
        content = f"선생: {self.user_choice}\n나: {self.bot_choice}\n\n{result_text} 후훗."
        logger.info(f"가위바위보 결과: 사용자({interaction.user.id}) {self.user_choice} vs 봇 {self.bot_choice} -> {result_text}")
        try:
            await interaction.response.edit_message(content=content, view=self) # attachments는 수정하지 않음
        except discord.NotFound:
            logger.warning(f"RPS 결과 메시지 수정 실패: 원본 메시지를 찾을 수 없습니다. (메시지 ID: {self.result_message.id if self.result_message else 'N/A'})")
        except Exception as e:
            logger.error(f"RPS 결과 메시지 수정 중 오류: {e}", exc_info=True)
        self.stop() # View의 상호작용 리스닝 중지

    @button(label="가위 ✂️", style=discord.ButtonStyle.primary, custom_id="rps_scissors_button")
    async def scissors_button(self, interaction: discord.Interaction, button_obj: Button):
        self.user_choice = "가위"
        await self.process_game(interaction)

    @button(label="바위 ✊", style=discord.ButtonStyle.primary, custom_id="rps_rock_button")
    async def rock_button(self, interaction: discord.Interaction, button_obj: Button):
        self.user_choice = "바위"
        await self.process_game(interaction)

    @button(label="보 🖐️", style=discord.ButtonStyle.primary, custom_id="rps_paper_button")
    async def paper_button(self, interaction: discord.Interaction, button_obj: Button):
        self.user_choice = "보"
        await self.process_game(interaction)

    async def on_timeout(self):
        if self.result_message: # result_message가 설정되어 있다면
            if self.user_choice is not None: # 이미 게임이 종료되었다면
                self.stop()
                return
            content = "으음... 선생, 너무 오래 고민하는걸? 가위바위보는 다음에 다시 하자~"
            for item in self.children:
                if isinstance(item, Button): item.disabled = True
            try:
                logger.info(f"RPS 게임 타임아웃 (사용자 ID: {self.author_id}, 메시지 ID: {self.result_message.id})")
                await self.result_message.edit(content=content, view=self, attachments=[]) # 타임아웃 시 GIF 제거
            except discord.NotFound: pass # 메시지가 이미 삭제된 경우
            except Exception as e: logger.error(f"RPS 타임아웃 메시지 수정 중 오류: {e}", exc_info=True)
        self.stop()

@bot.command(name='가위바위보', aliases=['rps'])
async def rock_paper_scissors(ctx: commands.Context):
    logger.info(f"!가위바위보 명령어 감지 (사용자: {ctx.author})")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gif_file_name = "rock_paper_scissors.gif" # img 폴더 내의 GIF
    gif_path = os.path.join(script_dir, IMAGE_DIR_NAME, gif_file_name) # 경로 수정: IMAGE_DIR_NAME 사용

    view = RPSView(author_id=ctx.author.id)
    initial_message_content = "으헤~ 나와 가위바위보 한 판 어때, 선생? 아래 버튼에서 골라봐!"
    rps_gif_file = None

    if os.path.exists(gif_path):
        try:
            if os.path.getsize(gif_path) < 7.8 * 1024 * 1024: # 약 7.8MB
                 rps_gif_file = discord.File(gif_path, filename=gif_file_name)
            else:
                logger.warning(f"가위바위보 GIF 파일 ({gif_path})이 너무 큽니다.")
                initial_message_content += f"\n(앗, 내 멋진 모습이 담긴 GIF가 너무 커서 못 보여주겠네... 상상해줘, 선생!)"
        except Exception as e:
            logger.error(f"가위바위보 GIF 파일 처리 중 오류: {e}", exc_info=True)
            initial_message_content += f"\n(가위바위보 GIF를 준비하다가 작은 문제가 생겼어, 선생...)"
    else:
        logger.warning(f"가위바위보 GIF 파일 ({gif_path})을 찾을 수 없습니다.")
        initial_message_content += f"\n(앗, 가위바위보 하는 내 모습이 담긴 그림을 못 찾았네... 상상해줘, 선생!)"
    try:
        if rps_gif_file:
            sent_message = await ctx.reply(initial_message_content, file=rps_gif_file, view=view, mention_author=False)
        else:
            sent_message = await ctx.reply(initial_message_content, view=view, mention_author=False)
        view.result_message = sent_message # View가 메시지를 수정할 수 있도록 참조 저장
    except discord.errors.HTTPException as e:
        if e.status == 413 or (e.text and "Request entity too large" in e.text):
            logger.warning(f"가위바위보 메시지/GIF 전송 실패: 파일 크기 초과.")
        else:
            logger.error(f"가위바위보 메시지/GIF 전송 중 Discord HTTP 에러: {e} (상태: {e.status})")
        await ctx.reply("가위바위보를 시작하려는데 디스코드에서 문제가 생겼나봐, 선생...", mention_author=False)
    except Exception as e:
        logger.error(f"가위바위보 메시지/GIF 전송 중 예기치 않은 오류: {e}", exc_info=True)
        await ctx.reply("가위바위보를 시작하려다가 알 수 없는 문제가 생겼어, 선생...", mention_author=False)

@rock_paper_scissors.error
async def rps_error(ctx, error):
    logger.error(f"가위바위보 명령어 처리 중 오류: {error} (원본: {error.original if hasattr(error, 'original') else 'N/A'})", exc_info=True)
    await ctx.reply("가위바위보를 하다가 뭔가 예상치 못한 문제가 발생했어, 선생...", mention_author=False)

# --- 주사위 기능 ---
@bot.command(name='주사위', aliases=['roll', 'dice'])
async def roll_dice(ctx: commands.Context, dice_str: str = "1d6"):
    num_dice, num_sides = 1, 6
    try:
        if 'd' in dice_str.lower():
            parts = dice_str.lower().split('d')
            num_dice_str = parts[0]
            num_sides_str = parts[1]
            num_dice = int(num_dice_str) if num_dice_str else 1 # "d6" 같은 경우 1d6으로 처리
            num_sides = int(num_sides_str)
        else:
            num_sides = int(dice_str) # "20" 같은 경우 1d20으로 처리
            num_dice = 1

        if not (1 <= num_dice <= 100 and 2 <= num_sides <= 1000):
            await ctx.reply("으음... 주사위 개수(1~100)나 면 수(2~1000)가 좀 이상한 것 같아, 선생.", mention_author=False)
            return
    except ValueError:
        await ctx.reply("주사위는 'NdM' (예: `2d6`) 또는 'N' (예: `20`) 형식으로 알려줘, 선생.\n그냥 `!주사위`라고 하면 6면체 주사위 하나를 굴릴게!", mention_author=False)
        return
    except Exception as e:
        logger.error(f"주사위 파싱 오류: {e} (입력: {dice_str})", exc_info=True)
        await ctx.reply("주사위 형식을 이해하지 못했어, 선생. `!도움`을 참고해줄래?", mention_author=False)
        return

    rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
    total = sum(rolls)
    logger.info(f"!주사위: {ctx.author}가 {num_dice}d{num_sides} 굴림 -> {rolls} (합: {total})")
    if num_dice == 1: reply_message = f"데구르르...🎲 주사위를 굴려서 **{total}**이(가) 나왔어, 선생!"
    else: reply_message = f"데구르르...🎲 주사위 {num_dice}개를 굴려서 나온 결과는 [{', '.join(map(str, rolls))}]이고, 총합은 **{total}**이야, 선생!"
    await ctx.reply(reply_message, mention_author=False)

# --- 사다리 타기 기능 ---
@bot.command(name='사다리', aliases=['ladder'])
async def ladder_game(ctx: commands.Context, *, full_input: str):
    logger.info(f"!사다리 명령어 감지 (사용자: {ctx.author}, 입력: '{full_input}')")
    try:
        if "->" not in full_input:
            await ctx.reply("으음... 참가자랑 결과를 '->' 기호로 나눠서 알려줘야 해, 선생! \n예시: `!사다리 철수 영희 -> 치킨 피자`", mention_author=False)
            return
        parts = full_input.split("->", 1)
        participants_str = parts[0].strip()
        outcomes_str = parts[1].strip()

        if not participants_str or not outcomes_str:
            await ctx.reply("참가자 명단이나 결과 명단 둘 다 채워줘야지, 선생!", mention_author=False)
            return

        participants = [p.strip() for p in participants_str.split() if p.strip()]
        outcomes = [o.strip() for o in outcomes_str.split() if o.strip()]

        if not participants or not outcomes: # 공백만 입력된 경우도 처리
            await ctx.reply("참가자나 결과가 하나도 없으면 사다리를 탈 수 없어, 선생.", mention_author=False)
            return

        if len(participants) != len(outcomes):
            await ctx.reply(f"어라? 참가자는 {len(participants)}명인데 결과는 {len(outcomes)}개네? 수가 똑같아야 공평하게 나눌 수 있어, 선생!", mention_author=False)
            return
        
        if len(participants) == 1:
            logger.info(f"사다리 결과 (1명): {participants[0]} -> {outcomes[0]}")
            await ctx.reply(f"후훗, {participants[0]} 선생은(는) **{outcomes[0]}**(이)야! 뭐, 혼자니까 당연한가? 으헤~", mention_author=False)
            return

        random.shuffle(outcomes)
        embed = discord.Embed(title="🪜 호시노의 사다리 타기 결과! 🪜", description="두근두근... 과연 누가 뭘 차지했을까, 선생?", color=discord.Color.gold())
        log_results = []
        for i in range(len(participants)):
            embed.add_field(name=f"👤 {participants[i]}", value=f"🎯  **{outcomes[i]}**", inline=False)
            log_results.append(f"{participants[i]} -> {outcomes[i]}")
        logger.info(f"사다리 결과 (참가자: {len(participants)}명): {', '.join(log_results)}")
        embed.set_footer(text="으헤~ 이번 사다리도 재밌었네, 선생!")
        await ctx.reply(embed=embed, mention_author=False)

    except Exception as e:
        logger.error(f"사다리 게임 처리 중 오류 발생: {e} (입력: {full_input})", exc_info=True)
        await ctx.reply("으음... 사다리 타다가 뭔가 복잡한 문제가 생긴 것 같아, 선생. 입력을 다시 확인해 줄래?", mention_author=False)

@ladder_game.error
async def ladder_game_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("사다리 타려면 참가자랑 결과를 알려줘야지, 선생! `!도움`에 사용법이 있다구~", mention_author=False)
    else:
        logger.error(f"사다리 게임 명령어에서 예기치 않은 오류: {error}", exc_info=True)
        await ctx.reply("사다리 타다가 알 수 없는 문제가 생겼어, 선생...", mention_author=False)

# --- 로그 보기 명령어 (관리자용) ---
@bot.command(name='로그')
async def show_logs(ctx: commands.Context, lines: int = 20):
    if not ADMIN_USER_ID:
        logger.warning(f"로그 명령어 시도 (사용자: {ctx.author}), ADMIN_USER_ID 미설정.")
        await ctx.reply("으음... 관리자 ID가 설정되어 있지 않아서 이 명령어를 사용할 수 없어.", mention_author=False)
        return

    if ctx.author.id != ADMIN_USER_ID:
        logger.warning(f"비관리자 로그 명령어 시도 (사용자: {ctx.author}, ID: {ctx.author.id})")
        await ctx.reply("으음... 선생은 이 명령어를 사용할 권한이 없어.", mention_author=False)
        return

    logger.info(f"관리자 {ctx.author}가 !로그 {lines}줄을 요청했습니다.")
    max_lines_to_show = 100 # 디스코드 메시지 및 파일 생성 부담 줄이기 위한 최대 줄 수
    min_lines_to_show = 1
    if lines < min_lines_to_show : lines = min_lines_to_show
    if lines > max_lines_to_show:
        lines = max_lines_to_show
        await ctx.send(f"한 번에 최대 {max_lines_to_show}줄까지만 표시할 수 있어, 선생. {max_lines_to_show}줄로 보여줄게.", ephemeral=True, mention_author=False)

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            log_lines = f.readlines()
        
        if not log_lines:
            await ctx.reply("로그 파일이 비어있어, 선생.", mention_author=False)
            return

        recent_logs_list = log_lines[-lines:]
        recent_logs_text = "".join(recent_logs_list)

        if not recent_logs_text.strip():
             await ctx.reply(f"최근 {lines}줄에 표시할 로그 내용이 없어 (빈 줄일 수 있음).", mention_author=False)
             return

        if len(recent_logs_text) > 1900: # 코드 블록 마커와 추가 텍스트, 여유 공간 고려
            temp_log_filename = f"temp_log_{ctx.author.id}_{random.randint(1000,9999)}.txt" # 파일명 중복 방지
            try:
                with open(temp_log_filename, "w", encoding="utf-8") as temp_f:
                    temp_f.write(f"--- {ctx.bot.user.name} 최근 로그 {len(recent_logs_list)}줄 ---\n")
                    temp_f.write(recent_logs_text)
                await ctx.reply(f"최근 로그 {len(recent_logs_list)}줄이 너무 길어서 파일로 보내줄게, 선생.", file=discord.File(temp_log_filename), mention_author=False)
                logger.info(f"로그 {len(recent_logs_list)}줄을 파일 '{temp_log_filename}'로 전송 (요청자: {ctx.author}).")
                os.remove(temp_log_filename)
            except Exception as e_file:
                logger.error(f"로그 파일 전송 중 오류: {e_file}", exc_info=True)
                await ctx.reply("로그가 너무 길어서 파일로 보내려 했는데, 문제가 생겼어...", mention_author=False)
        else:
            # 마크다운 문자 이스케이프 처리 및 코드 블록으로 감싸기
            escaped_logs = discord.utils.escape_markdown(recent_logs_text.strip())
            if not escaped_logs: # 이스케이프 후 내용이 없는 경우
                await ctx.reply(f"최근 {lines}줄에 표시할 로그 내용이 없어 (이스케이프 후 비어있음).", mention_author=False)
            else:
                await ctx.reply(f"📜 최근 로그 {len(recent_logs_list)}줄이야, 선생:\n```log\n{escaped_logs}\n```", mention_author=False)

    except FileNotFoundError:
        logger.warning(f"로그 파일 '{log_file_path}'를 찾을 수 없습니다. (!로그 명령어)")
        await ctx.reply(f"'{log_file_path}' 로그 파일을 찾을 수 없어, 선생.", mention_author=False)
    except Exception as e:
        logger.error(f"!로그 명령어 처리 중 오류: {e}", exc_info=True)
        await ctx.reply("로그를 가져오다가 문제가 발생했어, 선생...", mention_author=False)

@show_logs.error
async def show_logs_error(ctx, error):
    if isinstance(error, commands.BadArgument): # lines 인수가 숫자가 아닐 때
        await ctx.reply("으음... 로그 줄 수는 숫자로 알려줘야 해, 선생. 예: `!로그 30`", mention_author=False)
    else:
        logger.error(f"!로그 명령어에서 예기치 않은 오류: {error}", exc_info=True)
        await ctx.reply("로그를 보여주려다 알 수 없는 문제가 생겼어, 선생...", mention_author=False)


# --- 메시지 처리 이벤트 ---
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user: # 봇 자신의 메시지는 무시
        return

    # 명령어를 먼저 처리하도록 함
    await bot.process_commands(message)

    # 명령어가 처리되었다면 (ctx.valid가 True), 일반 대화 로직은 건너뜀
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # 일반 대화 처리 (멘션, DM, '?' 시작)
    is_mentioned = bot.user.mentioned_in(message)
    is_dm = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_dm or (message.content.startswith("?") and not ctx.command): # ctx.command로 이미 처리된 명령어인지 한번 더 확인
        user_id = str(message.author.id)
        
        if is_mentioned:
            processed_content = re.sub(r"<@!?%s>\s*" % bot.user.id, "", message.content).strip()
        else:
            processed_content = message.content.strip()

        # 멘션만 있고 내용이 없는 경우
        if not processed_content and is_mentioned and not message.attachments: # 첨부파일 없는 빈 멘션
            await message.reply("응? 불렀어, 선생? 후아암... 무슨 일이야?", mention_author=False)
            return

        # '?'만 입력된 경우 (명령어가 아닐 때) 또는 내용 없는 DM (첨부파일도 없을 때)
        if (processed_content == "?" and not is_mentioned and not is_dm and not message.attachments) or \
        (not processed_content and is_dm and not message.attachments):
            return
        
        # 내용이 있거나, 또는 내용이 없더라도 첨부파일이 있는 DM/멘션의 경우 (Gemini가 이미지 처리 가능하다면)
        if processed_content or message.attachments:
            # 현재 Gemini 모델은 텍스트만 처리하므로, 첨부파일은 무시하고 텍스트만 전달
            # 추후 Gemini가 이미지 입력을 지원하면 이 부분 수정 필요
            if not processed_content and message.attachments:
                # 이미지가 있지만 텍스트가 없는 경우, Gemini에게 전달할 텍스트가 없음
                # 이 경우, "그림 잘 봤어 선생~" 같은 기본 응답 또는 Gemini에게 이미지 설명 요청(미구현)
                # 현재는 아무것도 안하거나 간단한 응답
                # logger.info(f"사용자 {message.author}가 첨부파일만 보냈습니다. (내용 없음)")
                # await message.reply("으헤~ 그림이네! 멋진걸, 선생?", mention_author=False) # 예시 응답
                return # 일단은 무시

            bot_reply_text = await generate_response(user_id, processed_content, message_obj=message)
            if bot_reply_text:
                try:
                    await message.reply(bot_reply_text, mention_author=False)
                except discord.errors.HTTPException as e:
                    logger.error(f"응답 메시지 전송 실패 (Gemini 응답): {e}", exc_info=True)
                    if e.status == 400 and e.text and "In content: Must be non-empty." in e.text:
                        logger.warning(f"Gemini 응답이 비어있어 메시지 전송에 실패했습니다. (사용자 메시지: {processed_content[:50]})")
                    # 다른 HTTP 오류는 일단 무시하거나, 사용자에게 간단한 오류 메시지 전송
                    # await message.reply("으음... 대답하려는데 뭔가 문제가 생겼나봐, 선생.", mention_author=False)


if __name__ == "__main__":
    if not DISCORD_TOKEN: logger.critical(".env 파일에 DISCORD_TOKEN이 설정되지 않았습니다.")
    elif not GEMINI_API_KEY: logger.critical(".env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")
    else:
        try:
            logger.info("HoshinoBot을 시작합니다...")
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure:
            logger.critical("Discord 토큰이 유효하지 않습니다. .env 파일의 DISCORD_TOKEN을 확인해주세요.")
        except Exception as e:
            logger.critical(f"봇 실행 중 치명적인 오류 발생: {e}", exc_info=True)