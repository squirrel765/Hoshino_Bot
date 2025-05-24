#모델 바꾸는 기능 들어간 버전

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import re # 정규 표현식 모듈 추가
import traceback # 오류 추적 모듈 추가

# 로컬 모듈 임포트
from prompt import SYSTEM_PROMPT
from weather import forecast_today, city_map # forecast_today와 city_map 임포트

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("DISCORD_TOKEN과 GEMINI_API_KEY를 .env 파일에 반드시 설정하세요!")
    exit(1)

# Google Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- 모델 전환 로직 관련 전역 변수 ---
MODEL_NAMES = [
    'gemini-2.5-flash-preview-05-20',
    'gemini-2.0-flash-001',
    'gemma-3-27b-it', 
    'gemini-1.5-flash-002'
]
# 사용 가능한 모델만 필터링 (예: Gemma 모델은 현재 genai 라이브러리에서 직접 지원하지 않을 수 있음)
# 실제 사용 가능한 모델 목록은 genai.list_models() 등으로 확인하는 것이 좋습니다.
# 여기서는 일단 제공된 목록을 사용하되, Gemma 모델은 주석 처리했습니다.

current_model_index = 0 # 현재 사용 중인 MODEL_NAMES 리스트의 인덱스
gemini_model = None # 실제 모델 객체 (전역으로 관리)

# --- 모델 설정 전역 변수 ---
generation_config_global = genai.types.GenerationConfig(
    temperature=0.7,
    top_p=0.9,
    top_k=40,
    max_output_tokens=1000,
)
safety_settings_global = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]
SYSTEM_PROMPT_GLOBAL = SYSTEM_PROMPT

# 사용자별 대화 세션 저장용 (메모리 기반)
chat_sessions = {}

def initialize_model(model_idx_to_load: int):
    """
    지정된 인덱스의 모델을 로드하고 전역 변수를 업데이트합니다.
    성공 시 True, 실패 시 False를 반환합니다.
    """
    global gemini_model, current_model_index, chat_sessions

    if not (0 <= model_idx_to_load < len(MODEL_NAMES)):
        print(f"오류: 모델 인덱스 {model_idx_to_load}가 MODEL_NAMES 리스트 범위를 벗어났습니다.")
        return False

    model_name_to_try = MODEL_NAMES[model_idx_to_load]
    print(f"모델 초기화/변경 시도: {model_name_to_try} (인덱스: {model_idx_to_load})")
    try:
        new_model = genai.GenerativeModel(
            model_name=model_name_to_try,
            system_instruction=SYSTEM_PROMPT_GLOBAL,
            generation_config=generation_config_global,
            safety_settings=safety_settings_global
        )
        gemini_model = new_model
        current_model_index = model_idx_to_load

        if chat_sessions:
            print(f"모델이 '{model_name_to_try}'(으)로 변경되었습니다. 모든 기존 채팅 세션을 초기화합니다.")
            chat_sessions.clear()

        print(f"성공적으로 모델을 '{model_name_to_try}'(으)로 로드했습니다.")
        return True
    except Exception as e:
        print(f"모델 '{model_name_to_try}' 로드 실패: {e}")
        if "The model `gemma" in str(e) and "is not found" in str(e):
            print(f"참고: '{model_name_to_try}' 모델은 google.generativeai 라이브러리에서 직접 지원하지 않을 수 있습니다. Vertex AI 또는 다른 방법을 고려해야 합니다.")
        elif "API key not valid" in str(e):
            print("Gemini API 키가 유효하지 않습니다. .env 파일을 확인해주세요.")
        return False

def get_or_create_chat_session(user_id: str):
    if not gemini_model:
        print("오류: get_or_create_chat_session 호출 시 gemini_model이 None입니다. 모델 초기화가 필요합니다.")
        return None

    if user_id not in chat_sessions:
        try:
            chat_sessions[user_id] = gemini_model.start_chat(history=[])
            print(f"'{MODEL_NAMES[current_model_index]}' 모델로 새로운 채팅 세션을 시작합니다: {user_id}")
        except Exception as e:
            print(f"채팅 세션 시작 중 오류 ({user_id}): {e}")
            return None
    return chat_sessions[user_id]

async def generate_response(user_id: str, user_message: str, retry_count=0, original_error_model_index_for_retry=None):
    """
    날씨 요청을 우선 처리하고, 그 외에는 Gemini API를 사용하여 응답을 생성합니다.
    API 할당량/모델 상태 문제 또는 기타 오류 발생 시 모델을 변경하고 재시도합니다.
    """
    global current_model_index, gemini_model

    # 1. 날씨 요청 처리
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
    if not gemini_model:
        print("오류: 현재 활성화된 Gemini 모델이 없습니다. 응답 생성이 불가능합니다.")
        if retry_count == 0:
            print("봇 시작 시 모델 로드에 실패했을 수 있습니다. 모델 재초기화를 시도합니다.")
            if initialize_model_globally():
                print("모델 재초기화 성공. 응답 재생성 시도.")
                return await generate_response(user_id, user_message, retry_count + 1)
            else:
                print("모델 재초기화 실패. 응답 불가.")
                return "으앙... 지금은 머리가 너무 아파서 생각할 수가 없어, 선생... 나중에 다시 말 걸어줘."
        return "으앙... 지금은 머리가 너무 아파서 생각할 수가 없어, 선생... 나중에 다시 말 걸어줘."

    chat_session = get_or_create_chat_session(user_id)
    if not chat_session:
        return "으음... 선생이랑 대화 채널을 만드는 데 뭔가 문제가 생겼나 봐. 조금 있다 다시 시도해 줄래?"

    try:
        print(f"'{MODEL_NAMES[current_model_index]}' 모델에게 전달 (ID: {user_id}): {user_message}")
        gemini_response = await chat_session.send_message_async(user_message)

        if "API 할당량" in gemini_response.text and "모델 상태" in gemini_response.text:
            print(f"응답 내용에서 API 할당량/모델 상태 문제 감지: '{gemini_response.text}'")
            raise Exception("API 할당량, 모델 상태 등을 확인해주세요. (응답 내용 기반)")

        return gemini_response.text

    except Exception as e:
        error_message = str(e)
        error_type = type(e).__name__
        print(f"Gemini API 호출 중 오류 발생 (모델: {MODEL_NAMES[current_model_index]}, 사용자 ID: {user_id}): {error_type} - {error_message}")
        traceback.print_exc()

        error_str_lower = error_message.lower()
        
        quota_error_keywords = ["quota", "rate limit", "resource exhausted", "api 할당량", "모델 상태"]
        is_quota_or_model_issue = any(keyword in error_str_lower for keyword in quota_error_keywords)
        if "api 할당량, 모델 상태 등을 확인해주세요." in error_str_lower:
            is_quota_or_model_issue = True
        
        is_context_length_issue = "context length" in error_str_lower or "token" in error_str_lower or "size of the request" in error_str_lower
        is_safety_issue = "block" in error_str_lower or "safety" in error_str_lower
        is_api_key_issue = "api key not valid" in error_str_lower

        # 모델 변경을 시도해야 하는 경우 (할당량 문제 또는 기타 명시적으로 처리되지 않은 오류)
        if is_quota_or_model_issue or not (is_context_length_issue or is_safety_issue or is_api_key_issue):
            if is_quota_or_model_issue:
                print(f"API 할당량 또는 모델 상태 문제 감지. 다음 모델로 전환 시도 (현재 모델: {MODEL_NAMES[current_model_index]}).")
            else:
                # 이것이 '기타 오류'에 해당합니다.
                print(f"기타 오류 발생 (오류 유형: {error_type}, 내용: {error_message}). 다음 모델로 전환 시도 (현재 모델: {MODEL_NAMES[current_model_index]}).")

            # 재시도 루프를 위한 시작 모델 인덱스 설정
            # original_error_model_index_for_retry는 이 재귀 호출 체인에서 처음 오류가 발생한 모델의 인덱스
            if original_error_model_index_for_retry is None:
                original_error_model_index_for_retry = current_model_index
            
            tried_models_in_this_cycle = 0
            
            # 현재 모델 인덱스부터 시작하여 순환하며 다음 모델 시도
            for i in range(len(MODEL_NAMES)):
                next_model_idx_candidate = (current_model_index + 1 + i) % len(MODEL_NAMES)
                
                # 모든 모델을 한 바퀴 다 돌았는지 확인 (현재 모델로 돌아왔고, 최소 한 번은 다른 모델을 시도한 경우)
                if next_model_idx_candidate == original_error_model_index_for_retry and tried_models_in_this_cycle > 0 :
                    print("모든 가용 모델을 순회하며 시도했지만 오류가 지속됩니다.")
                    break # 루프 종료, 아래에서 최종 실패 메시지 반환

                print(f"모델 전환 시도: {MODEL_NAMES[next_model_idx_candidate]}")
                if initialize_model(next_model_idx_candidate):
                    print(f"모델이 성공적으로 {MODEL_NAMES[current_model_index]}(으)로 변경되었습니다. 메시지 재전송 시도.")
                    # 모델 변경 후에는 새 세션이 필요 (initialize_model에서 chat_sessions.clear() 호출)
                    return await generate_response(user_id, user_message, retry_count + 1, original_error_model_index_for_retry)
                else:
                    print(f"{MODEL_NAMES[next_model_idx_candidate]} 모델 로드 실패. 다음 모델을 시도합니다.")
                    tried_models_in_this_cycle += 1
                    # current_model_index는 initialize_model 실패 시 변경되지 않으므로,
                    # 다음 루프에서 (current_model_index + 1 + i) % len(MODEL_NAMES)는 다음 모델을 가리킴
            
            # 모든 모델을 시도했거나, 더 이상 시도할 모델이 없는 경우 (루프를 빠져나온 경우)
            print("모든 가용 모델을 시도했지만 실패했습니다.")
            return "흑흑... 내가 아는 모든 방법을 써봤는데도 지금은 대답하기가 너무 어려워, 선생... 정말 미안해, 나중에 다시 찾아와 줄래?"

        elif is_context_length_issue:
            print(f"컨텍스트/요청 크기 문제로 {user_id}의 세션을 초기화합니다.")
            if user_id in chat_sessions:
                del chat_sessions[user_id]
            return "으음... 방금 무슨 이야기 하고 있었지? 다시 말해줄래, 선생? 머리가 잠깐 하얘졌어~"
        elif is_safety_issue:
            return "으음... 선생, 그건 좀 대답하기 곤란한 내용인 것 같아. 다른 이야기 하자~"
        elif is_api_key_issue:
            print("치명적 오류: Gemini API 키가 유효하지 않습니다. 봇 관리자에게 문의하세요.")
            return "으앙... 선생님이랑 이야기하고 싶은데, 뭔가 중요한 연결이 끊어진 것 같아... 관리자 아저씨한테 한번 물어봐 줄래?"
        
        # 이 부분은 이론상 위의 조건들(should_switch_model 포함)에 의해 커버되어야 하지만,
        # 만약을 위한 최종 fallback (사실상 위의 should_switch_model이 True가 되어 모델 전환을 시도할 것임)
        print(f"처리되지 않은 특정 예외 유형입니다. 오류: {error_type} - {error_message}")
        return "우웅... 지금은 좀 피곤해서 대답하기 어렵네~ 나중에 다시 물어봐줘, 구만."


def initialize_model_globally():
    """봇 시작 또는 필요시 전역 모델을 초기화합니다."""
    global current_model_index # current_model_index를 업데이트하므로 global 선언
    initial_model_loaded = False
    
    # MODEL_NAMES 리스트를 순회하며 첫 번째 사용 가능한 모델을 찾습니다.
    for idx in range(len(MODEL_NAMES)):
        if initialize_model(idx): # initialize_model이 current_model_index를 설정
            initial_model_loaded = True
            break
        else:
            print(f"{MODEL_NAMES[idx]} 모델 로드에 실패했습니다. 다음 모델을 시도합니다.")
    
    if not initial_model_loaded:
        print("치명적 오류: 사용 가능한 Gemini 모델을 찾거나 로드할 수 없습니다. MODEL_NAMES 리스트와 API 키를 확인하세요.")
    return initial_model_loaded


@bot.event
async def on_ready():
    print(f'봇이 성공적으로 로그인했습니다: {bot.user.name} (ID: {bot.user.id})')
    
    if not initialize_model_globally():
        print("봇 초기화 중 모델 로드 실패. 일부 기능이 제한될 수 있습니다 또는 봇이 종료됩니다.")
        activity = discord.Game(name="모델 로드 실패! 점검 중...")
        await bot.change_presence(status=discord.Status.dnd, activity=activity)
        return
    else:
        print(f"봇 준비 완료. 현재 사용 모델: {MODEL_NAMES[current_model_index]}")
        activity = discord.Game(name="!도움 으로 사용법 확인!")
        await bot.change_presence(status=discord.Status.online, activity=activity)


@bot.command(name='초기화')
async def reset_chat_session(ctx: commands.Context):
    """사용자의 현재 대화 세션을 초기화합니다."""
    user_id = str(ctx.author.id)
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        await ctx.reply(f"기존 대화 내용을 잊어버렸어, 선생! ({MODEL_NAMES[current_model_index]} 모델과의 대화였어.) 새로운 마음으로 다시 시작하자~ 후후.", mention_author=False)
        print(f"채팅 세션이 초기화되었습니다: {user_id} (요청자: {ctx.author.name})")
    else:
        await ctx.reply("응? 아직 우리 대화 시작도 안 한 것 같은데, 선생? 아니면 이미 깨끗한 상태야!", mention_author=False)
        print(f"초기화 요청: 이미 세션이 없거나 초기화된 상태입니다: {user_id} (요청자: {ctx.author.name})")

@bot.command(name='도움')
async def show_help(ctx: commands.Context):
    """봇 사용법에 대한 도움말을 보여줍니다."""
    embed = discord.Embed(
        title="📘 호시노 봇 도움말 📘",
        description="으헤~호시노는 이런걸 할줄 안다구 선생!",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

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
    if gemini_model:
        embed.set_footer(text=f"현재 사용 모델: {MODEL_NAMES[current_model_index]}. 궁금한 게 있다면 언제든 아저씨에게 물어보라구~.")
    else:
        embed.set_footer(text="모델 로딩에 문제가 있어요... 궁금한 게 있다면 언제든 아저씨에게 물어보라구~.")


    await ctx.reply(embed=embed, mention_author=False)
    print(f"도움말 요청: {ctx.author.name} (ID: {ctx.author.id})")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)
    
    ctx = await bot.get_context(message)
    if ctx.command:
        return

    is_mentioned = bot.user.mentioned_in(message)
    is_dm = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_dm:
        if not gemini_model:
            print("on_message: gemini_model이 None입니다. 모델 초기화를 시도합니다.")
            if not initialize_model_globally():
                await message.reply("으앙... 지금은 아무 생각도 할 수가 없어... 관리자 아저씨한테 SOS 좀 쳐줄래?", mention_author=False)
                return
            else:
                print(f"on_message: 모델 재초기화 성공. 현재 모델: {MODEL_NAMES[current_model_index]}")

        user_id = str(message.author.id)
        
        if is_mentioned:
            processed_content = re.sub(rf'<@!?{bot.user.id}>', '', message.content).strip()
        else: 
            processed_content = message.content.strip()

        if not processed_content:
            if is_mentioned:
                await message.channel.send("응? 불렀어, 선생? 후아암... 무슨 일이야?")
            return

        async with message.channel.typing():
            bot_reply = await generate_response(user_id, processed_content)
        
        await message.reply(bot_reply, mention_author=False)


if __name__ == "__main__":
    # MODEL_NAMES 리스트에서 Gemma 모델 주석 처리 (genai 라이브러리 직접 지원 여부 불확실)
    # 만약 Vertex AI SDK 등을 사용한다면 해당 부분은 다르게 처리해야 합니다.
    # 여기서는 google.generativeai 라이브러리 기준입니다.
    if 'gemma-3-27b-it' in MODEL_NAMES:
        print("주의: 'gemma-3-27b-it' 모델은 google.generativeai 라이브러리에서 직접 지원되지 않을 수 있습니다. Vertex AI를 사용해야 할 수 있습니다.")
        # MODEL_NAMES = [name for name in MODEL_NAMES if name != 'gemma-3-27b-it'] # 리스트에서 제거하는 방법

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
            traceback.print_exc()