# reaction.py

import os
import discord
import random
import logging

logger = logging.getLogger('HoshinoBot.reaction')

REACTION_GIF_DIR = "reaction_gifs"

async def send_reaction_gif(ctx: discord.ext.commands.Context, target_user: discord.Member, reaction_name_upper: str): # reaction_name은 대문자로 받음
    """
    지정된 반응 이름 (대문자)에 해당하는 GIF (또는 이름으로 시작하는 GIF 중 랜덤)를 찾아
    대상 사용자에게 메시지를 보냅니다.
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    gif_folder_path = os.path.join(project_root, REACTION_GIF_DIR)

    if not os.path.exists(gif_folder_path) or not os.path.isdir(gif_folder_path):
        logger.warning(f"반응 GIF 폴더 '{gif_folder_path}'를 찾을 수 없습니다. (reaction.py에서 확인)")
        await ctx.send(f"으음... 반응에 쓸 그림들을 모아둔 폴더({REACTION_GIF_DIR})를 못 찾겠어, 선생.", ephemeral=True, mention_author=False)
        return None

    possible_gif_files = []
    try:
        for f_name in os.listdir(gif_folder_path):
            # 파일명이 reaction_name_upper로 시작하고 .gif로 끝나는지 확인 (대소문자 구분 없이)
            if f_name.upper().startswith(reaction_name_upper) and f_name.lower().endswith(".gif"):
                possible_gif_files.append(f_name)
    except Exception as e:
        logger.error(f"'{gif_folder_path}' 폴더에서 반응 GIF 목록을 가져오는 중 오류 발생: {e}", exc_info=True)
        await ctx.send("반응 GIF 폴더를 읽는 중에 문제가 생겼어, 선생.", ephemeral=True, mention_author=False)
        return None

    if not possible_gif_files:
        # 이 경우는 bot.py의 setup_hook에서 해당 reaction_name으로 시작하는 GIF가 하나도 없을 때 발생 가능
        # 또는 사용자가 !없는반응 @유저 입력 시 (이건 CommandNotFound로 처리됨)
        logger.info(f"'{reaction_name_upper}' 반응에 해당하는 GIF 파일을 찾을 수 없습니다. (폴더: {gif_folder_path})")
        # 사용자에게는 CommandNotFound가 뜨거나, setup_hook에서 명령어가 안 만들어짐.
        # 이 함수는 등록된 명령어를 통해서만 호출되므로, 파일이 없다는 건 setup_hook 로직 검토 필요.
        # 보통은 여기에 도달하지 않음.
        return None

    selected_gif_filename = random.choice(possible_gif_files)
    gif_path = os.path.join(gif_folder_path, selected_gif_filename)

    logger.info(f"선택된 반응 GIF: {selected_gif_filename} (요청: {reaction_name_upper}, 후보: {len(possible_gif_files)}개)")

    try:
        message_text = f"으헤~ {ctx.author.mention} 선생이 {target_user.mention} 선생에게 **{reaction_name_upper}**! (후훗)"
        
        if os.path.getsize(gif_path) > 7.8 * 1024 * 1024: 
            logger.warning(f"반응 GIF '{gif_path}' 파일 크기가 너무 큽니다 ({os.path.getsize(gif_path) / (1024*1024):.2f}MB).")
            await ctx.send(f"이 그림({reaction_name_upper})은 너무 커서 보여줄 수가 없어, 선생...", ephemeral=True, mention_author=False)
            return None

        reaction_file = discord.File(gif_path, filename=selected_gif_filename) # 파일명도 실제 선택된 파일명으로
        sent_message = await ctx.send(content=message_text, file=reaction_file, mention_author=False)
        logger.info(f"반응 GIF 전송: {ctx.author} -> {target_user} ({reaction_name_upper}, 파일: {selected_gif_filename})")
        return sent_message

    except FileNotFoundError: 
        logger.error(f"반응 GIF 파일 '{gif_path}'를 찾을 수 없습니다 (전송 시도 중).")
        await ctx.send(f"'{reaction_name_upper}' 그림을 찾았는데... 파일이 갑자기 사라졌나봐, 미안해 선생.", ephemeral=True, mention_author=False)
    except discord.errors.HTTPException as e:
        if e.status == 413 or (e.text and "Request entity too large" in e.text):
            logger.warning(f"반응 GIF '{gif_path}' 전송 실패: 파일 크기 초과 (Discord API).")
            await ctx.send(f"으... 이 그림({reaction_name_upper})은 너무 커서 보여줄 수가 없어, 선생. (8MB 초과)", ephemeral=True, mention_author=False)
        else:
            logger.error(f"반응 GIF 전송 중 Discord HTTP 에러: {e} (파일: {selected_gif_filename}, 상태: {e.status})")
            await ctx.send(f"'{reaction_name_upper}' 그림을 보내다가 디스코드에서 문제가 생겼어, 선생... ({e.status})", ephemeral=True, mention_author=False)
    except Exception as e:
        logger.error(f"반응 GIF 전송 중 예기치 않은 오류: {e} (파일: {selected_gif_filename})", exc_info=True)
        await ctx.send(f"'{reaction_name_upper}' 그림을 보내다가 알 수 없는 문제가 생겼어, 선생...", ephemeral=True, mention_author=False)
    
    return None