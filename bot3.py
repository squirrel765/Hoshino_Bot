# bot.py (또는 main.py)

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import re # 정규 표현식 모듈 추가

# 로컬 모듈 임포트
from prompt import SYSTEM_PROMPT
from weather import forecast_today, city_map # forecast_today와 city_map 임포트

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
# OpenWeatherMap API_KEY는 weather.py 내부에서 로드 및 사용됩니다.

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("DISCORD_TOKEN과 GEMINI_API_KEY를 .env 파일에 반드시 설정하세요!")
    exit(1)

# Google Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 읽기 권한
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents) # 명령어 접두사 '!' 사용

# Gemini 모델 설정 (봇 로드 시 한 번만 초기화)
generation_config = genai.types.GenerationConfig(
    temperature=0.7,
    top_p=0.9,
    top_k=40,
    max_output_tokens=1000, # 답변 최대 길이
)

safety_settings = [ # Gemini 안전 설정
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

try:
    gemini_model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest", # 또는 "gemini-pro"
        system_instruction=SYSTEM_PROMPT,
        generation_config=generation_config,
        safety_settings=safety_settings
    )
except Exception as e:
    print(f"Gemini 모델 로드 실패: {e}")
    print("Gemini API 키 또는 모델 이름을 확인하세요.")
    exit(1)


# 사용자별 대화 세션 저장용 (메모리 기반)
chat_sessions = {}

def get_or_create_chat_session(user_id: str):
    """사용자 ID에 대한 ChatSession을 가져오거나 새로 생성합니다."""
    if user_id not in chat_sessions:
        # 새 대화 세션 시작 (history는 세션 내에서 관리)
        chat_sessions[user_id] = gemini_model.start_chat(history=[])
        print(f"새로운 채팅 세션을 시작합니다: {user_id}")
    return chat_sessions[user_id]

async def generate_response(user_id: str, user_message: str):
    """날씨 요청을 우선 처리하고, 그 외에는 Gemini API를 사용하여 응답을 생성합니다."""

    # 1. 날씨 요청 처리 (정규 표현식 사용)
    supported_cities_kr = list(city_map.keys())

    if not supported_cities_kr:
        print("경고: weather.py의 city_map에 도시가 정의되어 있지 않습니다. 날씨 기능을 사용하기 어렵습니다.")
    else:
        cities_pattern_group = "|".join(re.escape(city) for city in supported_cities_kr)
        weather_pattern = re.compile(rf"(?i)\b({cities_pattern_group})\b\s*(?:은|는|이|가|의)?\s*날씨")
        
        match = weather_pattern.search(user_message)

        if match:
            found_city_kr = match.group(1)
            print(f"날씨 요청 감지: '{found_city_kr}' (원본 메시지: '{user_message}')")
            forecast_result = forecast_today(found_city_kr)
            return f"{forecast_result}\n{found_city_kr} 날씨 정보였어, 선생."

        elif user_message.strip().startswith("?") and "날씨" in user_message and not user_message.startswith(bot.command_prefix):
            default_city = "서울"
            if default_city in city_map:
                print(f"일반 날씨 요청 감지. 기본 도시 '{default_city}'로 조회합니다. (원본: '{user_message}')")
                forecast_result = forecast_today(default_city)
                return f"어떤 도시인지 정확히 안 알려줘서 일단 {default_city} 날씨를 가져왔어, 선생.\n{forecast_result}\n다른 도시가 궁금하면 '도시이름 날씨'라고 물어봐."
            else:
                print(f"경고: 기본 도시 '{default_city}'가 city_map에 없습니다.")
                return "날씨를 알려주고 싶은데, 어떤 도시인지 말해줄래, 선생? 예를 들면 '서울 날씨' 이렇게."

    # 2. 날씨 요청이 아니면 Gemini API에 위임
    chat_session = get_or_create_chat_session(user_id)
    try:
        print(f"Gemini에게 전달 (ID: {user_id}): {user_message}")
        gemini_response = await chat_session.send_message_async(user_message)
        return gemini_response.text
    except Exception as e:
        print(f"Gemini API 호출 중 오류 발생 (사용자 ID: {user_id}): {e}")
        error_str = str(e).lower()
        if "context length" in error_str or "token" in error_str or "size of the request" in error_str:
            print(f"컨텍스트/요청 크기 문제로 {user_id}의 세션을 초기화합니다.")
            if user_id in chat_sessions:
                del chat_sessions[user_id]
            return "으음... 방금 무슨 이야기 하고 있었지? 다시 말해줄래, 선생? 머리가 잠깐 하얘졌어~"
        elif "block" in error_str:
            return "으음... 선생, 그건 좀 대답하기 곤란한 내용인 것 같아. 다른 이야기 하자~"
        return "우웅... 지금은 좀 피곤해서 대답하기 어렵네~ 나중에 다시 물어봐줘, 구만."


@bot.event
async def on_ready():
    print(f'봇이 성공적으로 로그인했습니다: {bot.user.name} (ID: {bot.user.id})')
    activity = discord.Game(name="!도움 으로 사용법 확인!") # 봇 상태 메시지 변경
    await bot.change_presence(status=discord.Status.online, activity=activity)

# '!초기화' 명령어 정의
@bot.command(name='초기화')
async def reset_chat_session(ctx: commands.Context):
    """사용자의 현재 대화 세션을 초기화합니다."""
    user_id = str(ctx.author.id)
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        await ctx.reply("기존 대화 내용을 잊어버렸어, 선생! 새로운 마음으로 다시 시작하자~ 후후.", mention_author=False)
        print(f"채팅 세션이 초기화되었습니다: {user_id} (요청자: {ctx.author.name})")
    else:
        await ctx.reply("응? 아직 우리 대화 시작도 안 한 것 같은데, 선생? 아니면 이미 깨끗한 상태야!", mention_author=False)
        print(f"초기화 요청: 이미 세션이 없거나 초기화된 상태입니다: {user_id} (요청자: {ctx.author.name})")

# '!도움' 명령어 정의
@bot.command(name='도움')
async def show_help(ctx: commands.Context):
    """봇 사용법에 대한 도움말을 보여줍니다."""
    embed = discord.Embed(
        title="📘 호시노 봇 도움말 📘",
        description="으헤~호시노는 이런걸 할줄 안다구 선생!",
        color=discord.Color.blue()  # 또는 원하는 색상 discord.Color.from_rgb(r, g, b)
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url) # 봇 프로필 사진을 썸네일로 사용

    embed.add_field(
        name="💬 저와 대화하기",
        value=f"채널에서 저를 **멘션**(`@{bot.user.name}`)하거나 **DM**으로 메시지를 보내면 대답해드려요!\n"
            f"예: `@{bot.user.name} 오늘 기분 어때?`",
        inline=False
    )
    embed.add_field(
        name="☀️ 날씨 물어보기",
        value="`도시이름 날씨`라고 물어보세요. (예: `서울 날씨`, `부산 날씨`)\n"
            "그냥 `날씨`라고 물어보면 제가 임의로 서울 날씨를 알려드려요.\n"
            "(단, 제가 아는 도시여야 해요!)",
        inline=False
    )
    embed.add_field(
        name="🔄 대화 초기화",
        value="`!초기화` 라고 입력하면 저와의 이전 대화 내용을 잊어버리고 새로 시작할 수 있어요.",
        inline=False
    )
    embed.add_field(
        name="🙋 도움말 보기",
        value="`!도움` 이라고 입력하면 이 도움말을 다시 볼 수 있어요.",
        inline=False
    )
    embed.set_footer(text="궁금한 게 있다면 언제든 아저씨에게 물어보라구~.")

    await ctx.reply(embed=embed, mention_author=False)
    print(f"도움말 요청: {ctx.author.name} (ID: {ctx.author.id})")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if message.content.startswith(bot.command_prefix) and \
    any(cmd.name == message.content[len(bot.command_prefix):].split(' ')[0] for cmd in bot.commands):
        # 메시지가 등록된 명령어로 시작하면, 일반 응답 로직을 건너뜀
        return

    is_mentioned = bot.user.mentioned_in(message)
    is_dm = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_dm:
        user_id = str(message.author.id)
        
        if is_mentioned:
            processed_content = message.content.replace(f'<@{bot.user.id}>', '', 1)
            processed_content = processed_content.replace(f'<@!{bot.user.id}>', '', 1).strip()
        else:
            processed_content = message.content.strip()

        if not processed_content:
            # 멘션만 있고 내용이 없는 경우, 명령어가 아닌 일반 멘션으로 간주
            # (예: @봇이름)
            if is_mentioned and not message.content.startswith(bot.command_prefix):
                await message.channel.send("응? 불렀어, 선생? 후아암... 무슨 일이야?")
            return


        async with message.channel.typing():
            bot_reply = await generate_response(user_id, processed_content)
        
        await message.reply(bot_reply, mention_author=False)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print(".env 파일에 DISCORD_TOKEN이 설정되지 않았습니다.")
    elif not GEMINI_API_KEY:
        print(".env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")
    else:
        try:
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure:
            print("Discord 토큰이 유효하지 않습니다. .env 파일의 DISCORD_TOKEN을 확인해주세요.")
        except Exception as e:
            print(f"봇 실행 중 예상치 못한 오류 발생: {e}")