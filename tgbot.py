import logging
import os
import redis

from textwrap import dedent
from functools import partial

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardRemove
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ParseMode

from telegram.ext import Updater, CommandHandler, MessageHandler
from telegram.ext import Filters, CallbackContext, ConversationHandler
from telegram.ext import CallbackQueryHandler

from shop import get_products, get_product, get_product_image, put_product_in_cart
from shop import get_cart_description, delete_all_cart_products
from shop import get_cart_products, delete_cart_products, create_customer


logger = logging.getLogger(__name__)
redis_connect = None


def get_cart_menu(chat_id):
    base_url = redis_connect.get('base_url').decode('utf-8')
    cart = get_cart_description(base_url, chat_id)
    keyboard = []
    cart_products = []
    for _, item in enumerate(cart['data']['attributes']['products']['data']):
        product = get_cart_products(base_url, item['id'])
        cart_products.append(product['data'])
        keyboard.append([InlineKeyboardButton(
            f"Убрать из корзины {product['data']['attributes']['product']['data']['attributes']['title']}",
                  callback_data=f"del_from_cart|{item['id']}"
        )])
    keyboard.append([InlineKeyboardButton(
        f"Отказаться от заказа.", callback_data=f"cancel_cart"
    )])
    keyboard.append([InlineKeyboardButton('Оплатить', callback_data='payment')])

    message = ''
    total = 0
    for _, item in enumerate(cart_products):
        product = item['attributes']['product']['data']['attributes']
        message += f"{product['title']}\n {product['description']}\n "
        message += f"${product['price']} per kg. quantity { item['attributes']['quantity']}\n"
        cost = product['price'] * item['attributes']['quantity']
        total += cost
        message += f"Amount $ {cost}\n\n"

    message += f"Total: ${total}"
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def get_product_description(product_id):
    base_url = redis_connect.get('base_url').decode('utf-8')
    product = get_product(base_url, product_id)
    image = get_product_image(base_url, product_id)
    keyboard = [
        [InlineKeyboardButton('1 кг', callback_data=f'1000|{product_id}|weight'),
         InlineKeyboardButton('2 кг', callback_data=f'2000|{product_id}|weight'),
         InlineKeyboardButton('5 кг', callback_data=f'5000|{product_id}|weight')],
        [InlineKeyboardButton('Корзина', callback_data='cart'),
         InlineKeyboardButton('Назад', callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    product_description = f'{product}'[50]
    return product_description, image, reply_markup


def get_menu_buttons():
    base_url = redis_connect.get('base_url').decode('utf-8')
    products = get_products(base_url)
    keyboard = []
    for key, product in enumerate(products['data']):
        keyboard.append(
          [InlineKeyboardButton(
            product['attributes']['title'],
            callback_data=f"{product['id']}|product_id"
          )]
        )
    keyboard.append([InlineKeyboardButton('Перейти в корзину.', callback_data='cart')])
    return keyboard


def start(update: Update, context: CallbackContext):
    bot = context.bot
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
    keyboard = get_menu_buttons()
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(chat_id, text='You can choice product!', reply_markup=reply_markup)
    return 'HANDLE_DESCRIPTION'


def handle_cart(update: Update, context: CallbackContext):
    base_url = redis_connect.get('base_url').decode('utf-8')
    query = update.callback_query
    if not query:
      return 'HANDLE_CART'

    bot = context.bot
    chat_id = query.message.chat_id
    if query.data.find('cancel_cart') >= 0:
        delete_all_cart_products(base_url, chat_id)
        return start(update, context)
    elif query.data.find('del_from_cart') >= 0:
        delete_cart_products(base_url, query.data.split('|')[1])
    elif query.data == 'payment':
        bot.send_message(chat_id, text='Введите ваш e-mail')
        return 'WAIT_EMAIL'
    else:
        return 'HANDLE_CART'


def handle_menu(update: Update, context: CallbackContext):
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_MENU'
    chat_id = query.message.chat_id
    user_reply = query.data
    if user_reply:
        keyboard = get_menu_buttons()
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
    return 'HANDLE_DESCRIPTION'


def handle_users_reply(update: Update, context: CallbackContext):

    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return

    if user_reply == '/start':
        user_state = 'START'
        redis_connect.set(chat_id, user_state.encode('utf-8'))

    user_state = redis_connect.get(chat_id).decode('utf-8')
    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAIT_EMAIL': handle_wait_email,
    }
    state_handler = states_functions[user_state]
    try:
        user_state = state_handler(update, context)
        redis_connect.set(chat_id, user_state.encode('utf-8'))
    except Exception as err:
        logger.warning(f'Ошибка в работе телеграм бота\n{err}\n')


def handle_description(update: Update, context: CallbackContext):
    '''1000 2000 5000 grams cart back'''
    query = update.callback_query
    if not query:
        return 'HANDLE_DESCRIPTION'

    bot = context.bot
    chat_id = query.message.chat_id
    if query.data.find('product_id') >= 0:
        product_id = query.data.split('|')[0]
        product_description, image, reply_markup = get_product_description(product_id)
        bot.send_photo(chat_id=chat_id, photo=image, caption=product_description, reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        return 'HANDLE_DESCRIPTION'
    elif query.data.find('weight') >= 0:
        weight, product_id = query.data.split('|')
        weight, product_id = int(weight), product_id
        base_url = redis_connect.get('base_url').decode('utf-8')
        put_product_in_cart(base_url, product_id, weight, chat_id.__str__())
        bot.send_message(chat_id=chat_id, text='Product put to cart successfully.')
        return 'HANDLE_DESCRIPTION'
    elif query.data == 'back':
        bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        return start(update, context)
    elif query.data == 'cart':
        message, reply_markup = get_cart_menu(chat_id)
        bot.send_message(chat_id, text=message, reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        return 'HANDLE_CART'
    else:
        return 'HANDLE_DESCRIPTION'


def handle_wait_email(update: Update, context: CallbackContext):
    bot = context.bot
    query = update.callback_query
    if query and query.data == 'mail_yes':
        chat_id = query.message.chat_id
        customer_email = redis_connect.get(f'email_{chat_id}').decode()
        base_url = redis_connect.get('base_url').decode()
        first_name = name if (name := query.from_user.first_name) else ''
        last_name = name if (name := query.from_user.last_name) else ''
        customer_name = (first_name + ' ' + last_name).strip()
        customer_id = create_customer(base_url, customer_name, customer_email)
        redis_connect.set(f'customer_{chat_id}', customer_id)
        bot.send_message(text='Ожидайте уведомление на почте', chat_id=chat_id)
        bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        return 'HANDLE_MENU'
    elif query and query.data == 'mail_no':
        message = 'Пришлите, пожалуйста, ваш <b>email</b>'
        bot.send_message(text=message, chat_id=query.message.chat_id, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
        return 'WAIT_EMAIL'
    else:
        email = update.message.text
        message = dedent(f'''
        Вы прислали мне эту почту: <b>{email}</b>
        Всё верно?
        ''')
        chat_id = update.effective_chat.id
        redis_connect.set(f'email_{chat_id}', email)
        keyboard = [[InlineKeyboardButton('Верно', callback_data='mail_yes')],
                    [InlineKeyboardButton('Неверно', callback_data='mail_no')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return 'WAIT_EMAIL'


def help(update, callbackcontext):
    update.message.reply_text("Use /start to test this bot.")


def error(update, callbackcontext):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text(
        f'Good by., {update.message.from_user.first_name}!',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def start_bot():
    load_dotenv()
    get_database_connection()
    base_url = os.getenv('base_url')
    redis_connect.set('base_url', base_url)
    token = os.getenv('TG_TOKEN')
    updater = Updater(token)
    dispatcher = updater.dispatcher
    parameters = partial(
                handle_users_reply,
            )
    dispatcher.add_handler(CallbackQueryHandler(parameters))
    dispatcher.add_handler(MessageHandler(Filters.text, parameters))
    dispatcher.add_handler(CommandHandler('start', parameters))
    logger.info('Telegram market started.')
    updater.start_polling()
    updater.idle()


def get_database_connection():
    global redis_connect
    if redis_connect is None:
        redis_connect = redis.Redis(host=os.getenv('REDIS_HOST'), port=os.getenv('REDIS_PORT'), db=0)
    return redis_connect


if __name__ == '__main__':
    start_bot()
