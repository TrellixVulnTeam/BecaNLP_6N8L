import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader



class NeuralNetClassifier(object):
    """
        Clase madre de todos los clasificadores con redes
        neuronales implementados en PyTorch.
        Esta clase está pensada para entrenar modelos
        con una función de costo optimizada con algún
        método de gradiente descendiente y diferenciación automática).
    """

    def __init__(self, model, device):
        device, model = self._select_device(device, model)
        self.device = device
        self.model = model.to(device)

    def train(self, train_dataset, epochs=1, verbose=True, optim_algorithm='minibatch', **kwargs):
        """
        Función para entrenar el modelo.
        """

        model = self.model
        device = self.device

        # Definimos el dataloader:
        if optim_algorithm == 'SGD':
            batch_size = 1
        else:
            batch_size = kwargs.pop('batch_size',512)
        loader = DataLoader(train_dataset, batch_size, shuffle=True)

        # Seleccionamos el método de optimización:
        try:
            optimizer = self.optimizer
        except AttributeError:
            if optim_algorithm == 'minibatch' or optim_algorithm == 'SGD':
                optimizer = optim.SGD(model.parameters(), **kwargs)
            elif optim_algorithm == 'Adam':
                optimizer = optim.Adam(model.parameters(), **kwargs)
            else:
                raise TypeError('Algoritmo de optimización no soportado')
        model.train()

        try:
            current_epoch = self.current_epoch
        except AttributeError:
            current_epoch = 1

        # Inicializamos el historial de la loss:
        try:
            loss_history = self.loss_history
            print('Resuming training from epoch {}...'.format(current_epoch))
        except AttributeError:
            print('Starting training...')
            loss_history = []

        # Comenzamos el entrenamiento:
        zero_grad = optimizer.zero_grad
        step = optimizer.step
        loss_fn = self.loss

        try:

            for e in range(current_epoch, current_epoch+epochs):
                for t, (x,y) in enumerate(loader):
                    x = x.to(device)
                    y = y.to(device)

                    zero_grad() # Llevo a cero los gradientes de la red
                    scores = model(x) # Calculo la salida de la red
                    loss = loss_fn(scores,y) # Calculo el valor de la loss
                    loss.backward() # Calculo los gradientes
                    step() # Actualizo los parámetros

                    loss_history.append(loss.item())

                if verbose:
                    print('Epoch {} finished. Approximate loss: {:.4f}'.format(e, sum(loss_history[-5:])/len(loss_history[-5:])))

        
            print('Training finished')
            print()

        except KeyboardInterrupt:
            print('Exiting training...')
            print()

        self.model = model
        self.loss_history = loss_history
        self.optimizer = optimizer
        self.current_epoch = e + 1

    @staticmethod
    def _select_device(device, model):
        if device is None:
            device = torch.device('cpu')
            print('Warning: Dispositivo no seleccionado. Se utilizará la cpu.')
        elif device == 'parallelize':
            if torch.cuda.device_count() > 1:
                device = torch.device('cuda:0')
                model = nn.DataParallel(model)
            else:
                device = torch.device('cpu')
                print('Warning: No es posible paralelizar. Se utilizará la cpu.')
        elif device == 'cuda:0' or device == 'cuda:1':
            if torch.cuda.is_available():
                device = torch.device(device)
            else:
                device = torch.device('cpu')
                print('Warning: No se dispone de dispositivos tipo cuda. Se utilizará la cpu.')
        elif device == 'cpu':
            device = torch.device(device)
        else:
            raise RuntimeError('No se seleccionó un dispositivo válido')

        return device, model


    def save_checkpoint(self, filename):
        print('Saving checkpoint to file...',end=' ')
        model = self.model.to(torch.device('cpu'))
        torch.save({
            'epoch': self.current_epoch,
            'model_state_dict': model.state_dict(),
            'optimizer': self.optimizer,
            'loss': self.loss_history
            }, filename)
        print('OK')

    def load_checkpoint(self, filename):
        print('Loading checkpoint from file...',end=' ')
        checkpoint = torch.load(filename)
        self.current_epoch = checkpoint['epoch']
        model = self.model
        model.load_state_dict(checkpoint['model_state_dict'])
        self.model = model.to(self.device)
        self.optimizer = checkpoint['optimizer']
        self.loss_history = checkpoint['loss']
        print('OK')


    def save_parameters(self, filename):
        print('Saving parameters to file...',end=' ')
        model = self.model.to(torch.device('cpu'))
        torch.save(model.state_dict(), filename)
        print('OK')

    def load_parameters(self, filename):
        print('Loading parameters from file...',end=' ')
        model = self.model
        model.load_state_dict(torch.load(filename))
        self.model = model.to(self.device)
        print('OK')



    def predict(self, dataset):

        """
        Función para predecir nuevas muestras.

        NOTA: LA CONVENCIÓN ES QUE y_test E y_predict TIENEN LA FORMA (N,) YA SEAN
        TORCH TENSORS O NUMPY ARRAYS. CUANDO SE USAN PARA ENTRENAR UNA RED NEURONAL
        SE RESHEPEAN PARA TENER FORMA DE COLUMNA.


        """

        device = self.device
        model = self.model
        model.eval()

        x, _ = dataset[0]
        scores = model(x.to(device))
        if scores.dim() == 1: # (N,) para logistic regression
            make_predictions = lambda scores: (scores > 0).type(torch.long)
        elif scores.dim() == 2: # (N,C) para softmax
            make_predictions = lambda scores: scores.argmax(dim=1)
        else:
            raise RuntimeError('Score must have 1 or 2 dimensions: (N,) or (N,C).')

        n_samples = len(dataset)
        y_predict = torch.zeros(n_samples,dtype=torch.long)
        with torch.no_grad():
            for i in range(n_samples):
                x, _ = dataset[i]
                scores = model(x.to(device))
                y_predict[i] = make_predictions(scores)

        return y_predict


    def loss(self,scores,target):
        """
        Criterio de costo. Esto se pisa con la subclase
        """
        pass




class SequenceClassifier(NeuralNetClassifier):
    """
        Clase madre de todos los modelos implementados
        con redes neuronales para secuencias. Es una
        subclase de NeuralNetClassifier.
    """


    def _pad_collate_fn(data_batch):
        x_batch, y_batch = zip(*data_batch)
        x_lenghts = torch.tensor([sample.size(0) for sample in x_batch])
        sorted_lenghts_idx = torch.argsort(x_lenghts,descending=True)
        x_lenghts = x_lenghts[sorted_lenghts_idx]
        x_batch = nn.utils.rnn.pad_sequence(x_batch, batch_first=True)
        x_batch = x_batch[sorted_lenghts_idx]
        y_batch = y_batch[sorted_lenghts_idx]
        # y_batch tiene que tener por lo menos 2 dimensiones (el batch primero)
        y_lenghts = torch.tensor([sample.size(0) for sample in y_batch])
        return x_batch, x_lenghts, y_batch, y_lenghts

    def train(self, train_dataset, optim_algorithm='SGD',
              epochs=1, batch_size=512, **kwargs):
        """
        Función para entrenar el modelo.
        """

        model = self.model
        device = self.device

        # Definimos el dataloader:
        loader = DataLoader(train_dataset, batch_size,
            shuffle=True, collate_fn=_pad_collate_fn)

        # Seleccionamos el método de optimización:
        try:
            optimizer = self.optimizer
        except AttributeError:
            if optim_algorithm == 'SGD':
                optimizer = optim.SGD(model.parameters(), **kwargs)
            elif optim_algorithm == 'Adam':
                optimizer = optim.Adam(model.parameters(), **kwargs)
            else:
                raise TypeError('Algoritmo de optimización no soportado')
        model.train()

        try:
            current_epoch = self.current_epoch
        except AttributeError:
            current_epoch = 1

        # Inicializamos el historial de la loss:
        try:
            loss_history = self.loss_history
            print('Resuming training from epoch {}...'.format(current_epoch))
        except AttributeError:
            print('Starting training...')
            loss_history = []

        # Comenzamos el entrenamiento:
        try:

            for e in range(current_epoch, current_epoch+epochs):
                for t, (x, x_lenghts, y, y_lenghts) in enumerate(loader):
                    x = x.to(device)
                    y = y.to(device)

                    optimizer.zero_grad() # Llevo a cero los gradientes de la red
                    scores = model(x,x_lenghts) # Calculo la salida de la red
                    loss = self.loss(scores,x_lenghts,y,y_lenghts) # Calculo el valor de la loss
                    loss.backward() # Calculo los gradientes
                    optimizer.step() # Actualizo los parámetros

                    loss_history.append(loss.item())

                print('Epoch {} finished. Approximate loss: {:.4f}'.format(e, sum(loss_history[-5:])/len(loss_history[-5:])))

            print('Training finished')
            print()

        except KeyboardInterrupt:
            print('Exiting training...')
            print()

        self.model = model
        self.loss_history = loss_history
        self.optimizer = optimizer
        self.current_epoch = e + 1

    def loss(scores,scores_lenghts,target,target_lenghts):
        pass




class NaiveBayesClassifier(object):

    def __init__(self):
        if not hasattr(self,classifier):
            raise AttributeError('No se inicializó el modelo')

    def train(self,dataset):
        X, y = dataset
        self.classifier.fit(X,y)
        return self

    def predict(self,dataset):
        X, y = dataset
        y_predict = self.classifier.predict(X)
        return y, y_predict




class SVMClassifier(object):

    def __init__(self):
        if not hasattr(self,classifier):
            raise AttributeError('No se inicializó el modelo')


    def train(self,dataset,sample_weight=None):
        X, y = dataset
        self.classifier.fit(X,y,sample_weight)
        return self

    def predict(self,dataset):
        X, y = dataset
        y_predict = self.classifier.predict(X)
        return y, y_predict

