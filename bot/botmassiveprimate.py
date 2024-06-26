# !pip install pytelegrambotapi

import pandas as pd
import numpy as np
import telebot
from telebot import types
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.neighbors import BallTree
from sklearn.base import BaseEstimator

train_data = pd.read_csv("train_data.csv")
good = pd.read_csv("train_data.csv")

vectorizer = TfidfVectorizer()
vectorizer.fit(good.Question)
matrix_big = vectorizer.transform(good.Question)

svd = TruncatedSVD(n_components=180)
svd.fit(matrix_big)
matrix_small = svd.transform(matrix_big)

def softmax(x):
  proba = np.exp(-x)
  return proba / sum(proba)

class NeighborSampler(BaseEstimator):
  def __init__(self, k=5, temperature=1.0):
    self.k = k
    self.temperature = temperature
  def fit(self, X, y):
    self.tree_ = BallTree(X)
    self.y_ = np.array(y)
  def predict(self, X, random_state=None):
    distances, indices = self.tree_.query(X, return_distance=True, k=self.k)
    result = []
    for distance, index in zip(distances, indices):
      result.append(np.random.choice(index, p=softmax(distance * self.temperature)))
    return self.y_[result]

ns = NeighborSampler()
ns.fit(matrix_small, good.Answer)
pipe = make_pipeline(vectorizer, svd, ns)

bot = telebot.TeleBot('Your token for tg bot')

# Словарь для хранения состояний пользователей
user_states = {}

# Обработчик команд /start и /help
@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        user_states[user_id] = {}
    # Приветственное сообщение и описание доступных команд
    welcome_message = "Добро пожаловать! Я бот, созданный командой: \"Массив Приматов\" для вопросов и ответов.\n\n"
    welcome_message += "Доступные команды:\n"
    welcome_message += "/start или /help - для начала и подсказки.\n"
    welcome_message += "/question - Спроси у меня интересующий тебя вопрос и получи на него ответ.\n"
    welcome_message += "/answer - Проверим твои знания. Я задам тебе вопрос, а ты постараешься дать на него верный ответ, после твоего ответа, я скажу верный ли ответ ты дал.\n"
    welcome_message += "/test - Проверь свои знания, ответить на 5 вопросов и узнай свой результат.\n"
    bot.reply_to(message, welcome_message)
    # Создание клавиатуры
    keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
    button1 = types.KeyboardButton("/start")
    button2 = types.KeyboardButton("/help")
    button3 = types.KeyboardButton("/question")
    button4 = types.KeyboardButton("/answer")
    button5 = types.KeyboardButton("/stop")
    button6 = types.KeyboardButton("/test")
    keyboard.row(button1, button2)
    keyboard.add(button3, button4)
    keyboard.row(button5, button6)
    # Отправка сообщения с клавиатурой
    bot.reply_to(message, "Выберите одну из команд:", reply_markup=keyboard)

# Обработчик команды /stop - завершение диалога
@bot.message_handler(commands=['stop'])
def handle_stop(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    bot.reply_to(message, "Диалог завершен. Если у тебя возникнут еще вопросы ко мне – обращайся (пиши /start или /help).")

# Обработчик команды /question - спросить вопрос и получить на него ответ
@bot.message_handler(commands=['question'])
def handle_question(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['state'] = 'question'
    # Получаем случайный вопрос из good и сохраняем его
    question = good.sample(1)['Question'].iloc[0]
    user_states[user_id]['current_question'] = question
    bot.reply_to(message, 'Можешь спросить у меня вопрос по пройденному материалу:')
    user_states[user_id]['last_command'] = 'question'

# Обработчик команды /answer - получить вопрос от бота и дать ответ, дожидаясь вердикта
@bot.message_handler(commands=['answer'])
def handle_answer(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        user_states[user_id] = {}
    state = user_states[user_id].get('state')
    user_states[user_id]['last_command'] = 'answer'
    # Получаем случайный вопрос из good и сохраняем его
    question = good.sample(1)['Question'].iloc[0]
    user_states[user_id]['current_question'] = question
    # Отправляем вопрос пользователю
    bot.reply_to(message, question)
    bot.reply_to(message, "Введи свой ответ:")
    user_states[user_id]['state'] = 'waiting_answer'

# Обработчик команды /test - пройти тест из 5 вопросов
@bot.message_handler(commands=['test'])
def handle_test(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['state'] = 'test'
    user_states[user_id]['test_questions'] = []
    user_states[user_id]['correct_answers'] = 0
    user_states[user_id]['total_questions'] = 5  # Количество вопросов в тесте
    user_states[user_id]['current_question_index'] = 0
    for _ in range(user_states[user_id]['total_questions']):
        question = good.sample(1)['Question'].iloc[0]
        user_states[user_id]['test_questions'].append(question)
    def send_next_question(user_id):
        current_question_index = user_states[user_id]['current_question_index']
        bot.reply_to(message, "Следующий вопрос:")
        bot.reply_to(message, user_states[user_id]['test_questions'][current_question_index])
    # Отправляем вопрос из теста
    send_next_question(user_id)

# Вычисление косинусного сходства между двумя строками
def compute_similarity(answer1, answer2):
    # Преобразование строк в векторы TF-IDF
    vectorizer = TfidfVectorizer()
    vectorizer.fit([answer1, answer2])
    vector_answer1 = vectorizer.transform([answer1])
    vector_answer2 = vectorizer.transform([answer2])
    # Вычисление косинусного сходства между векторами
    similarity = cosine_similarity(vector_answer1, vector_answer2)
    return similarity[0][0]

# Обработчик всех текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        bot.reply_to(message, "Извини, но я не понял твоего вопроса, пжалуйста начни диалог с команды /start или /help.")
        return
    state = user_states.get(user_id, {}).get('state')
    last_command = user_states[user_id].get('last_command')
    if state == 'question' and last_command == 'question':
        answer = pipe.predict([message.text.lower()])[0]
        bot.reply_to(message, answer)
        bot.reply_to(message, "Если у тебя остались вопросы - задавай. Если нет - отправь /stop.")
    elif state == 'waiting_answer':
      # Получаем последний заданный вопрос
      last_question = user_states[user_id]['current_question']
      # Получаем ответ пользователя
      user_answer = message.text.lower()
      # Получаем список правильных ответов для данного вопроса
      correct_answers = good[good['Question'] == last_question]['Answer'].tolist()
      # Инициализируем переменную для лучшего сходства
      best_similarity = 0
      # Проходим по всем правильным ответам и находим наилучшее сходство
      for correct_answer in correct_answers:
          similarity = compute_similarity(user_answer, correct_answer)
          if similarity > best_similarity:
              best_similarity = similarity
      # Проверяем наилучшее сходство и отправляем соответствующее сообщение
      if best_similarity > 0.5:  # Порог сходства для признания ответа верным
          bot.reply_to(message, "Молодец! Ты ответил верно!")
      else:
          bot.reply_to(message, f"Увы твой ответ неверный. Один из верных ответов: {correct_answers[0]}")
      bot.reply_to(message, "Попробуй ответить на этот вопрос:")
      next_question = good.sample(1)['Question'].iloc[0]
      bot.reply_to(message, next_question)
      bot.reply_to(message, "Введи свой ответ:")
      user_states[user_id]['current_question'] = next_question
      user_states[user_id]['state'] = 'waiting_answer'
      bot.reply_to(message, "Или напиши /stop, если хочешь закончить отвечать.")
      user_states[user_id]['state'] = 'waiting_answer'
    elif state == 'test':
      current_question_index = user_states[user_id]['current_question_index']
      user_states[user_id]['current_question_index'] += 1  # Увеличиваем индекс текущего вопроса
      # Получаем последний заданный вопрос
      last_question = user_states[user_id]['test_questions'][current_question_index]
      # Получаем ответ пользователя
      user_answer = message.text.lower()
      # Получаем список правильных ответов для данного вопроса
      correct_answers = good[good['Question'] == last_question]['Answer'].tolist()
      # Инициализируем переменную для лучшего сходства
      best_similarity = 0
      # Проходим по всем правильным ответам и находим наилучшее сходство
      for correct_answer in correct_answers:
        similarity = compute_similarity(user_answer, correct_answer)
        if similarity > best_similarity:
          best_similarity = similarity
      # Проверяем, правильный ли ответ
      if best_similarity > 0.5:  # Порог сходства для признания ответа верным
        user_states[user_id]['correct_answers'] += 1
      if current_question_index != 4:
        bot.reply_to(message, "Следующий вопрос:")
        bot.reply_to(message, user_states[user_id]['test_questions'][current_question_index + 1])
      if current_question_index == 4:
        # Вычисляем балл
        score = user_states[user_id]['correct_answers']
        bot.reply_to(message, f"Тест завершен! Твой балл: {score}/{user_states[user_id]['total_questions']}")
        # Сбрасываем состояние пользователя
        del user_states[user_id]
        bot.reply_to(message, "Если у тебя возникнут еще вопросы ко мне – обращайся (пиши /start или /help).")
    else:
      bot.reply_to(message, "Извини, но я не понял твоего вопроса, пжалуйста начни диалог с команды /start или /help.")

# Запуск бота
bot.polling()
