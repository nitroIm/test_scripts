import lightgbm as lgb

class Model:
    def __init__(self):
        self.model = lgb.LGBMClassifier(random_state=42, verbose=-1, n_jobs=-1)

    def fit(self, X, y):
        self.model.fit(X, y)

    def predict(self, X):
        return self.model.predict(X)