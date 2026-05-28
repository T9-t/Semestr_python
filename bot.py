import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.upload import VkUpload
import random
import requests
import io
import time
import os
from datetime import datetime
from bs4 import BeautifulSoup

TOKEN = "..."

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)
upload = VkUpload(vk_session)

user_states = {}
help_text = "Варианты комманд:\n" \
            "привет -- Приветствие от бота\n" \
            "играть -- Начать играть в угадай покемона\n"

print("Бот запущен и слушает сообщения...")


def log_user_action(user_id, action_type, details):

    if not os.path.exists("logs"):
        os.makedirs("logs")

    file_path = f"logs/{user_id}.log"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_line = f"[{current_time}] [{action_type}] {details}\n"
    
    with open(file_path, "a", encoding="utf-8") as file:
        file.write(log_line)


def get_cards(name, user_id):

    correct_name = name.strip().capitalize()
    url = f"https://www.pokemon.com/us/pokemon-tcg/pokemon-cards?cardName={correct_name}"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pokemon.com/"
    })
    
    try:
        session.get("https://www.pokemon.com/us/pokemon-tcg", timeout=10)
        time.sleep(1)
        
        response = session.get(url, timeout=10)
        
        if not response.ok:
            print(f"[!] Сайт вернул ошибку: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        card_grid = soup.find("ul", class_="cards-grid")
        
        if not card_grid:
            send_message(user_id, message_text=f"Карточки для покемона '{correct_name}' не найдены.")
            return
        
        blocks = card_grid.find_all("li")

        count_blocks = 5
        if count_blocks > len(blocks):
            count_blocks = len(blocks)

        send_message(user_id, message_text=f"Найдены карточки на сайте. Отправляю первые {count_blocks}:")

        for i in range(count_blocks):
            block = blocks[i]
            img_tag = block.find("img")
            
            if img_tag:
                img_url = img_tag.get("src")
 
                if img_url:
                    send_message(user_id, message_text=f"Карточка №{i+1}", image_url=img_url)
                    time.sleep(0.5)

    except Exception as e:
        print(f"[!] Ошибка при парсинге оригинального сайта: {e}")
        send_message(user_id, message_text="Произошла ошибка при обработке данных с сайта.")
        

def get_random_pokemon():
    random_id = random.randint(1, 151) 
    url = f'https://pokeapi.co/api/v2/pokemon/{random_id}'

    try:
        response = requests.get(url)
        if response.ok:
            json_data = response.json()
            name = json_data["name"].capitalize()

            sprites = json_data.get("sprites", {})
            other = sprites.get("other", {})
            artwork = other.get("official-artwork", {})
            image_url = artwork.get("front_default")
            
            if not image_url:
                image_url = sprites.get("front_default")
                
            return name, image_url
        else:
            print(f"[!] Сайт PokeAPI ответил ошибкой: {response.status_code}")
    except Exception as e:
        print(f"[!] Ошибка подключения к PokeAPI: {e}")
    
    return None, None


def send_message(user_id, message_text="", image_url=None):
    
    attachment_str = None
    if image_url:
        try:
            response = requests.get(image_url, timeout=5)
            if response.ok:
                image_fp = io.BytesIO(response.content)
                image_fp.name = 'photo.jpg'

                photo = upload.photo_messages(photos=image_fp, peer_id=user_id)
                attachment_str = f"photo{photo[0]['owner_id']}_{photo[0]['id']}"
                
        except Exception as e:
            print(f"[!] Сбой загрузки картинки в ВК: {e}")

    try:
        vk.messages.send(
            peer_id=user_id,
            message=message_text,
            attachment=attachment_str,
            random_id=random.randint(1, 2 ** 31 - 1)
        )
        return True
    except Exception as e:
        print(f"[!] Сбой сети ВК при отправке: {e}")

    return False


for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        
        user_message = event.text.strip()
        user_message_lower = user_message.lower()
        user_id = event.user_id

        log_user_action(user_id, "ЗАПРОС", f"Пользователь написал: '{user_message}'")

        if user_id not in user_states:
            user_states[user_id] = {"step": "START", "secret_name": ""}

        current_step = user_states[user_id]["step"]

        if current_step == "GAME_GUESS":
            correct_name = user_states[user_id]["secret_name"]

            if user_message_lower == correct_name.lower():
                send_message(user_id, message_text=f"Правильно! Это был {correct_name.capitalize()}! Ты выиграл.")
                log_user_action(user_id, "ИГРА", f"Пользователь угадал покемона: {correct_name}")
            else:
                send_message(user_id, message_text=f"Неверно, ты проиграл! Правильный ответ был {correct_name.capitalize()}")
                log_user_action(user_id, "ИГРА", f"Проигрыш. Неверная попытка ответа: '{user_message}' (ожидалось: {correct_name})")

            send_message(user_id, message_text=f"Хочешь посмотреть карточки связаные с этим покемоном? (да/нет)")
            user_states[user_id]["step"] = "CARD"
            log_user_action(user_id, "КАРТОЧКИ", f"Пользователю предложенно посмотреть карточки к покемону '{correct_name}'")
            continue

        if current_step == "CARD":

            correct_name = user_states[user_id]["secret_name"]

            if user_message_lower == "Да".lower():
                send_message(user_id, message_text=f"Отлично! Сейчас сделаем.")
                get_cards(correct_name, user_id)

                log_user_action(user_id, "КАРТОЧКИ", f"Пользователь решил посмотреть карточки по покемону: {correct_name}")
                user_states[user_id] = {"step": "START", "secret_name": ""}
                
            elif user_message_lower == "Нет".lower():
                send_message(user_id, message_text=f"Хорошо, чем теперь хотите занятся.\n{help_text}")
                
                log_user_action(user_id, "КАРТОЧКИ", f"Пользователь решил не смотреть карточки по покемону: {correct_name}")
                user_states[user_id] = {"step": "START", "secret_name": ""}
            else: 
                send_message(user_id, message_text=f"Пожалуйста повторите ответ")
                log_user_action(user_id, "КАРТОЧКИ", f"Пользователь ответил: {user_message_lower}, переспросить")

            continue


        if user_message_lower == "привет":
            send_message(user_id, message_text="Привет! Я бот ВКонтакте.\n" \
            "Со мной ты можешь поиграть в угадай покемона и посмотреть карточки.")

        elif user_message_lower == "играть":
            send_message(user_id, message_text="Цель игры, написать имя покемона на картинке\n" \
            "Загружаю покемона, подожди секунду...")

            secret_name, pokemon_img = get_random_pokemon()
            
            if secret_name and pokemon_img:
                user_states[user_id] = {"step": "GAME_GUESS", "secret_name": secret_name}
                
                msg = "Игра началась! Кто этот покемон?\nНапиши его имя на английском:"
                send_message(user_id, message_text=msg, image_url=pokemon_img)
                log_user_action(user_id, "ИГРА", f"Загадано существо: {secret_name}")
            else:
                send_message(user_id, message_text="Что-то пошло не так. Не удалось запустить игру")
            
        else:
            send_message(user_id, message_text=help_text)