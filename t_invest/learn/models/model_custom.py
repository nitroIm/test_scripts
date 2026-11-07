import numpy as np

class Model:
    def fit(self, X, y):
        # Кастомная модель не требует обучения, только правила
        pass

    def predict(self, X):
        # Индексы: rsi=7, macd=8, macd_signal=9, volume_ratio=10
        rsi = X[:, 7]
        macd = X[:, 8]
        macd_sig = X[:, 9]
        vol_ratio = X[:, 10]
        # Покупаем, если RSI перепродан, MACD пересек сигнальную вверх, и объем выше среднего
        pred = ((rsi < 30) & (macd > macd_sig) & (vol_ratio > 1.2)).astype(int)
        return pred