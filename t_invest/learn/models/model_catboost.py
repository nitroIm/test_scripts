import catboost as cb

class Model:
    def __init__(self):
        self.model = cb.CatBoostClassifier(random_state=42, verbose=0)

    def fit(self, X, y):
        self.model.fit(X, y)

    def predict(self, X):
        return self.model.predict(X)