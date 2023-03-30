# -*- coding: utf-8 -*-
"""miniFrost.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1RONbFh5_K4BcELYcZ46ollXu1GMg9WPs

# miniFrost

I am hoping to build a mini GPT model alogn the lines of Karpathy's nanoGPT tutorial [here](https://www.youtube.com/watch?v=kCc8FmEb1nY). Instead of Shakespeare I will attempt to do Robert Frost's poems because they are more evocative to me.
"""

from google.colab import files
import pandas as pd
import torch
import torch.nn as nn
from torch.nn import functional as F
!pip install tiktoken
import tiktoken
import math

"""Read the data from the file and parse it. I am gonna print the first 5 lines."""

poem_collection = pd.read_csv("robert_frost_collection.csv")
print(poem_collection.head())

all_text = ""

# Clean the NaN value
poem_collection = poem_collection.drop(labels=0, axis=0)
for i, poem in enumerate(poem_collection['Content']):
  all_text = "\n".join([all_text, poem])

print("Length of the text: ", len(all_text))

fileout = open("poems.txt", "w")
fileout.write(all_text)
fileout.close()

# Extract all the unique characters that are in the text
uniq_chars = sorted(list(set(all_text)))
print(''.join(uniq_chars))

VOCAB_SIZE = len(uniq_chars)

"""### Encoding and Decoding Functions
These functions will be used to encode and decode the string to a list of integers. I will be using OpenAI's tiktoken library that uses sub-words. It will be shorter than encoding every possible character as its ASCII value.
"""

enc = tiktoken.get_encoding("gpt2")

STOI = { ch:i for i,ch in enumerate(uniq_chars)}
ITOS = { i:ch for i,ch in enumerate(uniq_chars)}
encode = lambda s: [STOI[c] for c in s]
decode = lambda l: ''.join([ITOS[i] for i in l])

"""### Build a Pytorch Tensor from the Encoded Text"""

encoded_text = encode(all_text)
data = torch.tensor(encoded_text)
print(data.shape, data.dtype)
print(data[:500])

"""### Training and Testing Split

At this point, we will have to decide on the training-testing split for the model. The tutorial says a 90-10 split should be a good enough one.

**Remember that we can alter this later on and see how "accurately" it can generate text as per our needs.**

"""

TRAINING_PORTION = 0.9
n = math.ceil(TRAINING_PORTION * len(data))

training_data = data[:n]
testing_data = data[n:]

"""### Context and Target

Now for a transformer, we need to chunk data in batches and feed it in with a context and the target output that the context "implies".
This is how the model learns. It sees all the context for that batch and sees all the targets and accordingly learns to predict.
"""

BLOCK_SIZE = 8

# An example here shows the context and target in actions
context = training_data[:BLOCK_SIZE]
target = training_data[1:BLOCK_SIZE + 1]
for i in range(len(context)):
    print("The context is ", context[:i+1], " and the target is ", target[i])

"""### Getting Batches

Now, what we want is to sample random batches from the text, get their context and their target and then build a stack out of them. Since our batch size is 8, we will have 8 columns.
We will set the no. of rows in the stack to 4. Pytorch will parallelize this process and *that's what makes transformers so good. The power of efficiency.*

**Extracting Batches**
The function `get_batch` will be used to either extract 4 blocks of size 8 and put them onto a stack togther. 2 [4x8] stacks will be returned. One being the context and the other being the target.
"""

BATCH_SIZE = 4
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(1337)

# get_batch will extract from either training or testing depending
# on the value of the split_type ('train' or 'test')
def get_batch(split_type):
  data = training_data if split_type == "train" else testing_data

  # ix essentially says: find $batch_size (4) random offsets and then
  # extract $block_size (8) length list after and including it.
  ix = torch.randint((len(data) - BLOCK_SIZE), (BATCH_SIZE, ))

  # Assemble the stacks: context (cx), target (tg)
  cx = torch.stack([data[i:i+BLOCK_SIZE] for i in ix])
  tg = torch.stack([data[i+1:i+BLOCK_SIZE+1] for i in ix])
  x, y = cx.to(DEVICE), tg.to(DEVICE)
  return x,y

# Sampling the
xd, yd = get_batch('train')

print(xd.shape)
print(xd)
print("---")
print(yd.shape)
print(yd)

for batch in range(BATCH_SIZE):
    for time in range(BLOCK_SIZE):
        context = xd[batch, :time+1]
        target = xd[batch, time]
        print(f'when the input is {context.tolist()} the expected out is {target.tolist()}')
    print()

EVAL_ITERS = 200

@torch.no_grad()
def estimate_loss(model_est):
    out = {}
    model_est.eval()
    for split in ['train', 'val']:
        losses = torch.zeros(EVAL_ITERS)
        for k in range(EVAL_ITERS):
            X, Y = get_batch(split)
            logits, loss = model_est(X, Y)
            losses[k] = loss.item()
        out[split] = losses.mean()
    model_est.train()
    return out

"""## Bigram Language Model

The simplest language model you can find. It literally just does word prediction based on the last word. Read more about n-gram models [here](https://towardsdatascience.com/introduction-to-language-models-n-gram-e323081503d9)
"""

N_EMBED = 32
class BigramLanguageModel(nn.Module):

    def __init__(self, vocab_size):
        super().__init__()
        # each token directly reads off the logits for the next token from a lookup table
        self.token_embedding_table = nn.Embedding(vocab_size, vocab_size)

    def forward(self, idx, targets=None):

        # idx and targets are both (B,T) tensor of integers
        logits = self.token_embedding_table(idx) # (B,T,C)

        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            logits = logits.view(B*T, C)
            targets = targets.view(B*T)
            loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, idx, max_new_tokens):
        # idx is (B, T) array of indices in the current context
        for _ in range(max_new_tokens):
            # get the predictions
            logits, loss = self(idx)
            # focus only on the last time step
            logits = logits[:, -1, :] # becomes (B, C)
            # apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1) # (B, C)
            # sample from the distribution
            idx_next = torch.multinomial(probs, num_samples=1) # (B, 1)
            # append sampled index to the running sequence
            idx = torch.cat((idx, idx_next), dim=1) # (B, T+1)
        return idx

model = BigramLanguageModel(VOCAB_SIZE)
m = model.to(DEVICE)
logits, loss = m(xd, yd)
print(logits.shape)
print(loss)

"""Now that we have a generation function, we can try generating some data. Of course it will be random data because we haven't trained our model but it will be useful. """

idx = torch.zeros((BLOCK_SIZE,BATCH_SIZE), dtype = torch.long)
print(idx)
print(decode(m.generate(idx = torch.zeros((1, 1), dtype=torch.long), max_new_tokens=500)[0].tolist()))

"""## Optimization

We can now start training the model and prompting it to minimizing the loss function. We will use the AdamW optimzer from PyTorch. The learning rate ca be set to much higher for
"""

# create an optimizer
optimizer = torch.optim.AdamW(m.parameters(), lr=1e-3)

"""Now in batches we can train the model to reduce the loss. """

MAX_ITERS = 3000
EVAL_INTERVAL = 300
for iter in range(MAX_ITERS):

    # every once in a while evaluate the loss on train and val sets
    if iter % EVAL_INTERVAL == 0:
        losses = estimate_loss(model)
        print(f"step {iter}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")

    # sample a batch of data
    xb, yb = get_batch('train')

    # evaluate the loss
    logits, loss = model(xb, yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

# generate from the model
context = torch.zeros((1, 1), dtype=torch.long, device=DEVICE)
print(decode(m.generate(context, max_new_tokens=500)[0].tolist()))

"""Now lets try outputing again"""

idx = torch.zeros((1,1), dtype = torch.long)
sequence_gen = m.generate(idx, max_new_tokens=100)[0].tolist()
print(decode(sequence_gen))

"""## Self-Attention and Transformer Networks

Now we want the batches to talk to each other. So if I am at batch i, i want to gain context and loss information of the predications of **all the previous batches** because I am trying to improve the predictions for this one.

I **cannot look at all the predictions in the future batches** because I want to predict the future.
"""

torch.manual_seed(1337)
B,T,C = 4,8,2 # batch = 4, time = 8 and channel = 2
x = torch.randn(B,T,C)
x.shape
print(x)

"""Now lets calculate the mean logits and use its values for each subsequent time column."""

weights = torch.tril(torch.ones(T,T))
print(weights)
weights = weights / weights.sum(1, keepdim=True)
print(weights)

# This is valid matrix multiplication becasue PyTorch will automatically convert
# the weights (T x T) matrix to a (B x T x T) so it can multiply with a
# (B x T x C) matrix
xbow_2 = weights @ x
print(xbow_2[0])

tril = torch.tril(torch.ones(T,T))
weights = torch.zeros(T, T)

# This essentially says that token in the future cannot communicate with a token
# in the past. We can't have a future token interacting with the past for the
# reasons mentioned before.
weights = weights.masked_fill(tril==0, float('-inf'))
weights = F.softmax(weights, dim=-1)

print(weights)
xbow3 = weights @ x
print(xbow3)

"""## Self-Attention

The value v stores "here's what I will communicate to you if there is a key that satsifies my query" for a single head.
"""

# version 4: self-attention!
torch.manual_seed(1337)
B,T,C = 4,8,32 # batch, time, channels
x = torch.randn(B,T,C)

# A single Head performs self-attention
head_size = 16
key = nn.Linear(C, head_size, bias=False)
query = nn.Linear(C, head_size, bias=False)
value = nn.Linear(C, head_size, bias=False)
k = key(x)   # (B, T, 16)
q = query(x) # (B, T, 16)
weights =  q @ k.transpose(-2, -1) # (B, T, 16) @ (B, 16, T) ---> (B, T, T)

tril = torch.tril(torch.ones(T,T))
weights = weights.masked_fill(tril==0, float('-inf'))
weights = F.softmax(weights, dim=-1)

v = value(x)
out = weights @ v

print(out.shape)
tril

weights[0]

"""Look at the 0.2391 in the last row of the above matrix. It is the 8th token. It knows its position via the position embedding table and the its value. Then it makes a query - like im looking for <> characters.
Every node gets to emit a key and the query and key that dot product the highest indicate that they match well.
"""

class Head(nn.Module):

  def __init__(self, head_size):
    super().__init__()
    self.query = nn.Linear(N_EMBED, head_size, bias=False)
    self.key = nn.Linear(N_EMBED, head_size, bias=False)
    self.value = nn.Linear(N_EMBED, head_size, bias=False)
    self.register_buffer('tril', torch.tril(torch.ones(BLOCK_SIZE, BLOCK_SIZE)))

  def forward(self, x):
    B,T,C = x.shape
    k = self.key(x)
    q = self.query(x)
    v = self.value(x)
    # compute attention scores ("affinities")

    # this is in accordance with what is done in the original transformers paper
    # the diision by the square root serves to amplify the maximum.
    wei = q @ k.transpose(-2,-1) * C**-0.5 # (B, T, C) @ (B, C, T) -> (B, T, T)
    wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf')) # (B, T, T)
    wei = F.softmax(wei, dim=-1) # (B, T, T)

    out = wei @ v
    return out


class MultiAttentionHead(nn.Module):

    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])

    def forward(self, x):
        return torch.cat([h(x) for h in self.heads], dim=-1)


class FeedForward(nn.Module):
    """ a simple mutlilayer perceptron"""

    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, n_embd),
            nn.ReLU(),
        )

    def forward(self, x):
        return self.net(x)


'''
Bigram Model with Self attention head
'''
class SABigramLanguageModel(nn.Module):

    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(VOCAB_SIZE, N_EMBED)
        self.position_embedding_table = nn.Embedding(BLOCK_SIZE, N_EMBED)
        self.sa_heads = MultiAttentionHead(4, N_EMBED//4) # 4 heads of 8-dimensional heads
        self.ffd = FeedForward(N_EMBED)
        self.lm_head = nn.Linear(N_EMBED, VOCAB_SIZE)

    def forward(self, idx, targets=None):
        B, T = idx.shape

        tok_emb = self.token_embedding_table(idx)
        pos_emb = self.position_embedding_table(torch.arange(T, device=DEVICE))
        x = tok_emb + pos_emb
        x = self.sa_heads(x)
        x = self.ffd(x)
        logits = self.lm_head(x)

        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            logits = logits.view(B*T, C)
            targets = targets.view(B * T)
            loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, idx, max_new_tokens):
        # idx is (B, T) array of indices in the current context
        for _ in range(max_new_tokens):
            # crop idx to the last block_size tokens
            idx_cond = idx[:, -BLOCK_SIZE:]
            # get the predictions
            logits, loss = self(idx_cond)
            # focus only on the last time step
            logits = logits[:, -1, :] # becomes (B, C)
            # apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1) # (B, C)
            # sample from the distribution
            idx_next = torch.multinomial(probs, num_samples=1) # (B, 1)
            # append sampled index to the running sequence
            idx = torch.cat((idx, idx_next), dim=1) # (B, T+1)
        return idx

xd, yd = get_batch('train')
sa_model = SABigramLanguageModel()
sa_m = sa_model.to(DEVICE)
logits, loss = sa_m(xd, yd)
print(logits.shape)
print(loss)

"""Define the same optimizer again

"""

