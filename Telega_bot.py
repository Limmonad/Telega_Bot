import logging
import asyncio
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
import json
import httpx
from aiogoogletrans import Translator

BAD_WORDS = {
    "блядь",
    "сука",
    "хуй",
    "ебать",
    "пидор",
    "мразь",
    "чмо",
    "залупа",
    "уебок",
}


translator = Translator()  # Создаём один экземпляр

async def translate(text: str, *, src="en", dest="ru") -> str:
    translated = await translator.translate(text, src=src, dest=dest)
    return translated.text

def has_bad_words(text: str) -> bool:
    lower_text = text.lower()
    return any(bad_word in lower_text for bad_word in BAD_WORDS)


# Загружаем конфиг
with open('TelegramBotRecipe.json', 'r') as f:
    config = json.load(f)

API_URL = config["FAST_API_URL"]
API_URL_ALCH = config["API_URL_ALCH"]
TOKEN = config["TOKEN_BOT"]
API_KEY = config["API_KEY_PROM"]  # 🔑 секретный ключ API
API_KEY_ALCH = config["API_KEY_TEST"]
API_RANDOM_MEALDB = config["API_RANDOM_MEALDB"]


logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния
class RecipeForm(StatesGroup):
    title = State()
    description = State()
    cuisine_type = State()
    meal_type = State()
    prep_time = State()
    ingredients = State()
class IngredientSearch(StatesGroup):
    input_ingredient = State()
    choose_recipe = State()



main_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text="🍳 Создать рецепт"),
            types.KeyboardButton(text="🔍 Найти рецепт")
        ],
        [
            types.KeyboardButton(text="Поиск по ингредиенту")  # новая кнопка
        ]
    ],
    resize_keyboard=True
)


CUISINE_OPTIONS = ["Итальянская", "Русская", "Французская", "Японская", "Мексиканская","Грузинская", "Другое(Ввод вручную)"]
MEAL_OPTIONS = ["Завтрак", "Обед", "Ужин", "Перекус", "Другое(Ввод вручную)"]



@dp.message(Command("random_recipe"), StateFilter("*"))
async def cmd_random_recipe(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 Ищу случайный рецепт...")

    try:
        # Получение рецепта
        async with httpx.AsyncClient() as client:
            resp = await client.get(API_RANDOM_MEALDB, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        meal = data["meals"][0]

        # Основные данные
        name_en = meal["strMeal"]
        category_en = meal["strCategory"]
        cuisine_en = meal["strArea"]
        instructions_en = meal["strInstructions"]

        # Собираем ингредиенты для перевода
        ingredients_list = []
        for i in range(1, 21):
            ingredient = meal.get(f"strIngredient{i}")
            if ingredient and ingredient.strip():
                ingredients_list.append(ingredient)

        # Параллельный перевод всех текстов
        translations = await asyncio.gather(
            translate(name_en),
            translate(category_en),
            translate(cuisine_en),
            translate(instructions_en),
            *[translate(ing) for ing in ingredients_list]
        )

        # Распаковываем результаты перевода
        name_ru, category_ru, cuisine_ru, instructions_ru = translations[:4]
        ingredients_translated = translations[4:4 + len(ingredients_list)]

        # Формируем список ингредиентов с переводами
        ingredients = []
        for i in range(len(ingredients_list)):
            measure = meal.get(f"strMeasure{i + 1}")
            ingredients.append(
                f"- {ingredients_translated[i]} ({ingredients_list[i]}): "
                f"{measure if measure else 'по вкусу'}"
            )

        # Формируем текст с рецептом
        result_text = (
                f"🍽️ <b>{name_ru}</b> ({name_en})\n\n"
                f"<b>Тип кухни:</b> {cuisine_ru}\n"
                f"<b>Категория:</b> {category_ru}\n\n"
                f"<b>Ингредиенты:</b>\n" + "\n".join(ingredients) + "\n\n"
        )

        # Добавляем инструкцию с ограничением длины
        max_instructions_length = 300
        if len(instructions_ru) > max_instructions_length:
            # Находим последнюю точку перед максимальной длиной
            last_dot = instructions_ru.rfind('.', 0, max_instructions_length)
            if last_dot > 0:
                instructions_part = instructions_ru[:last_dot + 1]
            else:
                instructions_part = instructions_ru[:max_instructions_length] + "..."

            result_text += f"<b>Приготовление:</b>\n{instructions_part}\n\n"
            result_text += "Продолжение в следующем сообщении..."
        else:
            result_text += f"<b>Приготовление:</b>\n{instructions_ru}"

        # Отправка сообщения с фото
        if meal.get("strMealThumb"):
            await message.answer_photo(
                photo=meal["strMealThumb"],
                caption=result_text,
                parse_mode="HTML"
            )
        else:
            await message.answer(result_text, parse_mode="HTML")

        # Если инструкция была обрезана, отправляем продолжение
        if len(instructions_ru) > max_instructions_length:
            remaining_text = instructions_ru[last_dot + 1 if last_dot > 0 else max_instructions_length:]
            await message.answer(f"<b>Продолжение приготовления:</b>\n{remaining_text}", parse_mode="HTML")

    except Exception as e:
        logging.error(f"Error in random_recipe: {e}", exc_info=True)
        await message.answer("⚠️ Не удалось получить рецепт. Попробуйте позже.")
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для создания и поиска рецептов.\n\n"
        "Используй кнопки внизу👇",
        reply_markup=main_menu
    )


@dp.message(Command("help"), StateFilter("*"))
async def cmd_help(message: types.Message, state: FSMContext):
    help_text = (
        "ℹ️ Доступные действия:\n\n"
        "🍳 Создать рецепт — введи данные пошагово\n"
        "🔍 Найти рецепт — ищи по названию блюда\n"
        "🧂 Поиск по ингредиенту — найди рецепт по одному из ингредиентов\n\n"
        "В меню слева можно выбрать случайный рецепт\n\n"
        "👇 Используй кнопки ниже для навигации."
    )
    await message.answer(help_text, reply_markup=main_menu)



@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите название рецепта для поиска:")
    await state.set_state("search_title")


@dp.message(F.text.lower() == "🍳 создать рецепт", StateFilter("*"))
async def create_recipe(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите название рецепта:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RecipeForm.title)


@dp.message(F.text.lower() == "🔍 найти рецепт", StateFilter("*"))
async def find_recipe(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите название рецепта для поиска:")
    await state.set_state("search_title")


# Поиск рецепта с авторизацией
@dp.message(StateFilter("search_title"))
async def process_search(message: types.Message, state: FSMContext):
    query = message.text.strip()
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(API_URL, params={"title": query}, headers=headers)
        resp.raise_for_status()
        recipes = resp.json()
        if not recipes:
            await message.answer("❌ Рецепты не найдены.", reply_markup=main_menu)
        else:
            for r in recipes:
                ingredients = "\n".join(
                    [f"- {i['name']}: {i['quantity']}" for i in r.get("ingredients", [])]
                )
                text = (
                    f"🍽️ <b>{r['title']}</b>\n"
                    f"Описание: {r.get('description', 'нет')}\n"
                    f"Тип кухни: {r.get('cuisine_type', 'нет')}\n"
                    f"Прием пищи: {r.get('meal_type', 'нет')}\n"
                    f"Время приготовления: {r.get('prep_time_minutes', 'нет')} мин.\n"
                    f"Ингредиенты:\n{ingredients}"
                )
                await message.answer(text, parse_mode="HTML")
    except requests.RequestException as e:
        await message.answer(f"Ошибка при запросе: {e}")
    await state.clear()


@dp.message(StateFilter(RecipeForm.title))
async def process_title(message: types.Message, state: FSMContext):
    title = message.text.strip()

    if has_bad_words(title):
        await message.answer("⚠️ Название содержит неприемлемые слова. Пожалуйста, введите другое название.")
        return  # остаёмся в том же состоянии для повторного ввода

    await state.update_data(title=title)
    await message.answer("Название принято\n Введите описание рецепта (или 'нет'):")
    await state.set_state(RecipeForm.description)



@dp.message(StateFilter(RecipeForm.description))
async def process_description(message: types.Message, state: FSMContext):
    desc = message.text if message.text.lower() != "нет" else None
    await state.update_data(description=desc)

    cuisine_kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=c)] for c in CUISINE_OPTIONS],
        resize_keyboard=True
    )
    await message.answer("Выберите тип кухни:", reply_markup=cuisine_kb)
    await state.set_state(RecipeForm.cuisine_type)


@dp.message(StateFilter(RecipeForm.cuisine_type))
async def process_cuisine(message: types.Message, state: FSMContext):
    ctype = message.text if message.text != "Другое" else None
    await state.update_data(cuisine_type=ctype)

    meal_kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=m)] for m in MEAL_OPTIONS],
        resize_keyboard=True
    )
    await message.answer("Выберите тип приема пищи:", reply_markup=meal_kb)
    await state.set_state(RecipeForm.meal_type)


@dp.message(StateFilter(RecipeForm.meal_type))
async def process_meal_type(message: types.Message, state: FSMContext):
    mtype = message.text if message.text != "Другое" else None
    await state.update_data(meal_type=mtype)
    await message.answer("Введите время приготовления в минутах или 'нет':", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RecipeForm.prep_time)


@dp.message(StateFilter(RecipeForm.prep_time))
async def process_prep_time(message: types.Message, state: FSMContext):
    if message.text.lower() == "нет":
        prep_time = None
    else:
        if not message.text.isdigit():
            await message.answer("Введите число или 'нет':")
            return
        prep_time = int(message.text)
    await state.update_data(prep_time_minutes=prep_time)
    await message.answer(
        "Введите ингредиенты в формате 'Название Количество', по одному в сообщении.\n"
        "Когда закончите, отправьте 'готово'."
    )
    await state.update_data(ingredients=[])
    await state.set_state(RecipeForm.ingredients)


@dp.message(StateFilter(RecipeForm.ingredients))
async def process_ingredients(message: types.Message, state: FSMContext):
    if message.text.lower() == "готово":
        data = await state.get_data()
        if not data.get("ingredients"):
            await message.answer("Добавьте хотя бы один ингредиент.")
            return

        recipe_json = {
            "title": data["title"],
            "description": data.get("description"),
            "cuisine_type": data.get("cuisine_type"),
            "meal_type": data.get("meal_type"),
            "prep_time_minutes": data.get("prep_time_minutes"),
            "ingredients": data["ingredients"]
        }

        try:
            resp = requests.post(API_URL, json=recipe_json, headers={"X-API-Key": API_KEY})
            resp.raise_for_status()
            res_json = resp.json()
            await message.answer(
                f"✅ Рецепт '{res_json.get('title')}' успешно создан!",
                reply_markup=main_menu
            )
        except requests.RequestException as e:
            await message.answer(f"Ошибка при сохранении: {e}", reply_markup=main_menu)

        await state.clear()
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Неправильный формат. Введите название и количество через пробел.\n"
            "Например:\nМука 200г"
        )
        return

    name = parts[0]
    quantity = parts[1]

    data = await state.get_data()
    ingredients = data.get("ingredients", [])
    ingredients.append({"name": name, "quantity": quantity})
    await state.update_data(ingredients=ingredients)

    done_keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Готово")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await message.answer(
        f"✅ Ингредиент '{name}' добавлен.\nДобавьте следующий или нажмите 'Готово'.",
        reply_markup=done_keyboard
    )


@dp.message(F.text.lower() == "поиск по ингредиенту", StateFilter("*"))
async def search_by_ingredient_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите ингредиент для поиска рецептов:")
    await state.set_state(IngredientSearch.input_ingredient)


@dp.message(StateFilter(IngredientSearch.input_ingredient))
async def process_ingredient_input(message: types.Message, state: FSMContext):
    ingredient = message.text.strip()
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(f"{API_URL_ALCH}/recipes/search_by_ingredient/", params={"ingredient": ingredient}, headers=headers)
        resp.raise_for_status()
        recipes = resp.json()

        if not recipes:
            await message.answer("❌ Рецепты не найдены по такому ингредиенту.", reply_markup=main_menu)
            await state.clear()
            return

        # Сохраняем рецепты в состояние
        await state.update_data(recipes=recipes)

        # Делаем клавиатуру с названиями рецептов
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text=r["title"])] for r in recipes],
            resize_keyboard=True
        )

        await message.answer("Выберите рецепт из найденных:", reply_markup=keyboard)
        await state.set_state(IngredientSearch.choose_recipe)

    except requests.RequestException as e:
        await message.answer(f"Ошибка при запросе: {e}", reply_markup=main_menu)
        await state.clear()


@dp.message(StateFilter(IngredientSearch.choose_recipe))
async def show_selected_recipe(message: types.Message, state: FSMContext):
    selected_title = message.text.strip()

    try:
        response = requests.get(
            url=API_URL,
            headers={"X-API-Key": API_KEY},
            params={"title": selected_title}
        )
        response.raise_for_status()
        recipe = response.json()
        print(recipe)

        texts = []

        for r in recipe:
            ingredients = "\n".join(
                [f"- {i['name']}: {i['quantity']}" for i in r.get("ingredients", [])]
            )
            text = (
                f"🍽️ <b>{r['title']}</b>\n"
                f"Описание: {r.get('description', 'нет')}\n"
                f"Тип кухни: {r.get('cuisine_type', 'нет')}\n"
                f"Прием пищи: {r.get('meal_type', 'нет')}\n"
                f"Время приготовления: {r.get('prep_time_minutes', 'нет')} мин.\n"
                f"Ингредиенты:\n{ingredients}"
            )
            texts.append(text)

        await message.answer("\n\n".join(texts), parse_mode="HTML", reply_markup=main_menu)
        await state.clear()


    except requests.RequestException as e:
        await message.answer(f"❌ Ошибка при получении рецепта: {e}", reply_markup=main_menu)
        await state.clear()






@dp.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    await message.answer(
        "Я вас не понял.\n\n"
        "Используйте кнопки меню или вызовите /help.",
        reply_markup=main_menu
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
