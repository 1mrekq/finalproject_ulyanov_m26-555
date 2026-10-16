import datetime
import hashlib

exchange_rates = {
    'BTC': 1.3,
    'UTC': 1
}


class User:
    _user_id: int
    _username: str
    _hashed_password: str
    _salt: str
    _registration_date: datetime

    def __init__(self, user_id: int, username: str, password: str, salt: str, registration_date: datetime):
        self.user_id = user_id
        self.username = username
        self._salt = salt
        self._registration_date = registration_date
        
        self.change_password(password)

    @property
    def user_id(self):
        return self._user_id

    @user_id.setter
    def user_id(self, value):
        if not isinstance(value, int):
            raise ValueError('Идентификатор пользователя должен быть int')
        
        self.user_id = value
        
    @property
    def username(self):
        return self._username
        
    @username.setter
    def username(self, value):
        if not isinstance(value, str):
            raise ValueError('Имя пользователя должно быть строкой')
        
        if len(str) == 0:
            raise ValueError('Имя пользователя не может быть пустым')
        
        self._username = value

    def get_user_info(self):
        return {
            'user_id': self.user_id,
            'user_name': self.username,
            'registration_data': self.registration_date
        }

    def change_password(self, new_password: str):
        if not isinstance(new_password, str):
                    raise ValueError('Имя пользователя должно быть строкой')
                
        if len(new_password) < 4:
            raise ValueError('Пароль должен быть не короче 4 символов')
        
        self._hashed_password = hashlib.sha256(new_password + self.salt)

    def verify_password(self, password: str):
        return self._hashed_password == hashlib.sha256(password + self._salt)


class Wallet:
    currency_code: str
    _balance: float
    
    def __init__(self, balance: float, currency_code: str):
        self.balance = balance
        pass
    
    @property
    def balance(self, value: float):
        if not isinstance(value, float):
            raise ValueError('Баланс должен быть float')
        
        if value < 0:
            raise ValueError('Баланс должен быть положительным числом')
        
        self._balance = value
        
    
    def deposit(self, amount: float):
        self.balance = amount
    
    def withdraw(self, amount: float):
        if self.balance - amount <= 0:
            raise ValueError('Сумма снятия превышает баланс')
            
        self.balance -= amount
    
    def get_balance_info(self):
        return f'{self.balance} {self.currency_code}'
    
    
class Portfolio:
    _user: User
    _wallets: dict[str, Wallet]
    
    def __init__(self, user: User):
        self.u_ser = user
        
    @property
    def user(self):
        return self._user

    @property
    def wallets(self):
        return self._wallets
    
    def add_currency(self, currency_code: str):
        if self._wallets(currency_code):
            raise ValueError('Данная валюта уже существует в кошельке')
    
    def get_total_value(self, base_currency='USD'):
        if not exchange_rates.get(base_currency):
            raise ValueError(f'Курс данной валюты не определен')
        
        return self._wallets.get(base_currency).balance * exchange_rates.get(base_currency)
    
    def get_wallet(self, currency_code):
        return self._wallets.get(currency_code)