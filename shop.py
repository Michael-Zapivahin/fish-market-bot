import os
from dotenv import load_dotenv

import requests


def delete_cart_products(base_url, cart_product_id):
  response = requests.delete(f'{base_url}/api/cart-products/{cart_product_id}')
  response.raise_for_status()
  return response.json()


def get_cart_products(base_url, cart_product_id):
    response = requests.get(f'{base_url}/api/cart-products/{cart_product_id}?populate=*')
    response.raise_for_status()
    return response.json()


def get_product(base_url, product_id):
    response = requests.get(f'{base_url}/api/products/{product_id}')
    response.raise_for_status()
    raw_product = response.json().get('data')
    return raw_product


def get_product_image(base_url, image_id):
    response = requests.get(f'{base_url}/api/products/{image_id}?populate=*')
    response.raise_for_status()
    image_link = response.json().get('data').get('attributes').get('picture').get('data').get('attributes').get('url')
    response = requests.get(f'{base_url}{image_link}', stream=True)
    response.raise_for_status()
    return response.content


def get_products(base_url):
    response = requests.get(f'{base_url}/api/products')
    response.raise_for_status()
    return response.json()


def put_product_in_cart(base_url, product_id, quantity, cart_id, user_id):
    url = f'{base_url}/api/cart-products'
    body = {
      "data": {
              'quantity': float(quantity/1000),
              'type': 'cart_product_item',
              'product': {
                'connect': [product_id]
              },
              'cart': {
                'connect': [get_cart(base_url, user_id, cart_id)]
              },
            }
          }
    response = requests.post(url, json=body)
    response.raise_for_status()
    return response.json()


def get_cart_description(base_url, user_id, tg_id):
    cart_id = get_cart(base_url, user_id, tg_id)
    url = f'{base_url}/api/carts/{cart_id}'
    body = {
      'data': {
        'populate': '*',
      }
    }
    response = requests.post(url, json=body)
    response.raise_for_status()
    return response.json()


def get_cart(base_url, user_id, tg_id):
    url = f'{base_url}/api/carts'
    body = {
      'data': {
        'filters[tg_id][$eq]': f'{tg_id}',
      }
    }
    response = requests.post(url, json=body)
    response.raise_for_status()
    cart = response.json()

    if cart['data']:
        return cart['data'][0]['id']

    body = {
      'data': {
        'tg_id': tg_id,
        'type': 'cart_item',
        'user': {
          'connect': [user_id]
        },
      }
    }
    response = requests.post(url, json=body)
    response.raise_for_status()
    return response.json()['data']['id']


def delete_all_cart_products(base_url, tg_id):
    url = f'{base_url}/api/carts?filters[tg_id][$eq]={tg_id}'
    response = requests.get(url)
    response.raise_for_status()
    cart_id = response.json()['data']['id']
    url = f'{base_url}/api/carts/{cart_id}?populate=*'
    response = requests.get(url)
    response.raise_for_status()
    cart_products = response.json()
    for _, item in enumerate(cart_products['data']):
        delete_cart_products(base_url, item['data']['id'])


def create_customer(base_url, customer_name, customer_email):
    url = f'{base_url}/users?filters[email][$eq]={customer_email}'
    response = requests.get(url)
    response.raise_for_status()
    if response['data']:
        print(f'Пользователь с адресом {customer_email} уже зарегистрирован.')
        return response['data']['id']

    url = f'{base_url}/api/users'
    body = {"data": {
                        'username': customer_name,
                        'type': 'user',
                        'email': customer_email
    }}
    response = requests.post(url, json=body)
    response.raise_for_status()
    return response.json().get('data').get('id')













