# import libraries
import nltk
nltk.download('punkt')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')

# import libraries
import numpy as np
import pandas as pd
pd.set_option('display.max_columns', 500)

import sys
import os
import re
from sqlalchemy import create_engine
import pickle

from scipy.stats import gmean
# import relevant functions/modules from the sklearn
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix
from sklearn.metrics import fbeta_score, make_scorer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, AdaBoostClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.feature_extraction.text import TfidfTransformer, CountVectorizer
from sklearn.multioutput import MultiOutputClassifier
from sklearn.base import BaseEstimator,TransformerMixin


def load_data(database_filepath):
     """
    Load Data from the Database
    
    Arguments:
        database_filepath -> Path to SQLite destination database (e.g. DisasterResponse.db)
    Output:
        X -> a dataframe containing features
        Y -> a dataframe containing labels
        category_names -> List of categories name
    """
    
    engine = create_engine('sqlite:///' + database_filepath)
    df = pd.read_sql_table('DisasterResponse',engine)
    
    #Remove child alone as it has all zeros only
    df = df.drop(['child_alone'],axis=1)
    
    # Given value 2 in the related field are neglible so it could be error. Replacing 2 with 1 to consider it a valid response.
    # Alternatively, we could have assumed it to be 0 also. In the absence of information I have gone with majority class.
    df['related']=df['related'].map(lambda x: 1 if x == 2 else x)
    
    X = df['message']
    y = df.iloc[:,4:]
    
    #print(X)
    #print(y.columns)
    category_names = y.columns # This will be used for visualization purpose
    return X, y, category_names



def tokenize(text):
    # Extract the word tokens from the provided text
    tokens = nltk.word_tokenize(text)
    
    #Lemmanitizer to remove inflectional and derivationally related forms of a word
    lemmatizer = nltk.WordNetLemmatizer()

    # List of clean tokens
    clean_tokens = [lemmatizer.lemmatize(w).lower().strip() for w in tokens]
    return clean_tokens

# Build a custom transformer which will extract the starting verb of a sentence
class StartingVerbExtractor(BaseEstimator, TransformerMixin):
    """
    Starting Verb Extractor class
    
    This class extract the starting verb of a sentence,
    creating a new feature for the ML classifier
    """

    def starting_verb(self, text):
        sentence_list = nltk.sent_tokenize(text)
        for sentence in sentence_list:
            pos_tags = nltk.pos_tag(tokenize(sentence))
            first_word, first_tag = pos_tags[0]
            if first_tag in ['VB', 'VBP'] or first_word == 'RT':
                return True
        return False

    # Given it is a tranformer we can return the self 
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X_tagged = pd.Series(X).apply(self.starting_verb)
        return pd.DataFrame(X_tagged)



def build_model():
     """
    Build Pipeline function
    
    Output:
        A Scikit ML Pipeline that process text messages and apply a classifier.
        
    """
    model = Pipeline([
        ('features', FeatureUnion([

            ('text_pipeline', Pipeline([
                ('count_vectorizer', CountVectorizer(tokenizer=tokenize)),
                ('tfidf_transformer', TfidfTransformer())
            ])),

            ('starting_verb_transformer', StartingVerbExtractor())
        ])),

        ('classifier', MultiOutputClassifier(AdaBoostClassifier()))
    ])

    return model

def multioutput_fscore(y_true,y_pred,beta=1):
    """
    MultiOutput Fscore
    
    This is a performance metric of my own creation.
    It is a sort of geometric mean of the fbeta_score, computed on each label.
    
    It is compatible with multi-label and multi-class problems.
    It features some peculiarities (geometric mean, 100% removal...) to exclude
    trivial solutions and deliberatly under-estimate a stangd fbeta_score average.
    The aim is avoiding issues when dealing with multi-class/multi-label imbalanced cases.
    
    It can be used as scorer for GridSearchCV:
        scorer = make_scorer(multioutput_fscore,beta=1)
        
    Arguments:
        y_true -> List of labels
        y_prod -> List of predictions
        beta -> Beta value to be used to calculate fscore metric
    
    Output:
        f1score -> Calculation geometric mean of fscore
    """
    
    # If provided y predictions is a dataframe then extract the values from that
    if isinstance(y_pred, pd.DataFrame) == True:
        y_pred = y_pred.values
    
    # If provided y actuals is a dataframe then extract the values from that
    if isinstance(y_true, pd.DataFrame) == True:
        y_true = y_true.values
    
    f1score_list = []
    for column in range(0,y_true.shape[1]):
        score = fbeta_score(y_true[:,column],y_pred[:,column],beta,average='weighted')
        f1score_list.append(score)
        
    f1score = np.asarray(f1score_list)
    f1score = f1score[f1score<1]
    
    # Get the geometric mean of f1score
    f1score = gmean(f1score)
    return f1score



def evaluate_model(model, X_test, Y_test, category_names):
     """
    Evaluate Model function
    
    This function applies a ML pipeline to a test set and prints out the model performance (accuracy and f1score)
    
    Arguments:
        pipeline -> A valid scikit ML Pipeline
        X_test -> Test features
        Y_test -> Test labels
        category_names -> label names (multi-output)
    """
    Y_pred = model.predict(X_test)
    
    multi_f1 = multioutput_fscore(Y_test,Y_pred, beta = 1)
    overall_accuracy = (Y_pred == Y_test).mean().mean()

    print('Average overall accuracy {0:.2f}%'.format(overall_accuracy*100))
    print('F1 score (custom definition) {0:.2f}%'.format(multi_f1*100))

    # Print the whole classification report.
    Y_pred = pd.DataFrame(Y_pred, columns = Y_test.columns)
    
    for column in Y_test.columns:
        print('Model Performance with Category: {}'.format(column))
        print(classification_report(Y_test[column],Y_pred[column]))




def save_model(model, model_filepath):
     """
    Save Pipeline function
    
    This function saves trained model as Pickle file, to be loaded later.
    
    Arguments:
        pipeline -> GridSearchCV or Scikit Pipelin object
        pickle_filepath -> destination path to save .pkl file
    
    """
    pickle.dump(model, open(pickle_filepath, 'wb'))


def main():
    if len(sys.argv) == 3:
        database_filepath, model_filepath = sys.argv[1:]
        print('Loading data...\n    DATABASE: {}'.format(database_filepath))
        X, Y, category_names = load_data(database_filepath)
        X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2)
        
        print('Building model...')
        model = build_model()
        
        print('Training model...')
        model.fit(X_train, Y_train)
        
        print('Evaluating model...')
        evaluate_model(model, X_test, Y_test, category_names)

        print('Saving model...\n    MODEL: {}'.format(model_filepath))
        save_model(model, model_filepath)

        print('Trained model saved!')

    else:
        print('Please provide the filepath of the disaster messages database '\
              'as the first argument and the filepath of the pickle file to '\
              'save the model to as the second argument. \n\nExample: python '\
              'train_classifier.py ../data/DisasterResponse.db classifier.pkl')


if __name__ == '__main__':
    main()