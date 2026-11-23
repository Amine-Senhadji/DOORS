# Disclaimer

This project was built for the UBS AI Financial Twin Challenge (LauzHack 2026). It is an independent project, not affiliated with, endorsed by, or reviewed by UBS.

## The data

The synthetic data and the starter kit were produced by [Stefania Stan](https://www.linkedin.com/in/stefania-s/), challenge author and information owner, and are included with her permission. They are not data about the customers of a bank, and they are not presented here as the data or the product of a bank.

All people and figures are fictional. Alexia does not exist, and no data about a real person is in this repository.

## What Doors computes

Doors computes scenarios under assumptions. Each assumption is listed in the application with its nature and its source, and can be changed there. The result is not a forecast: the worlds it tests are stress tests chosen by hand, not frequencies; the rules it uses for taxes, pensions and insurance are simplified; and several Swiss figures are marked as not verified. The known limits are listed in [docs/LIMITS.md](docs/LIMITS.md).

## Not advice

Nothing in this project is financial advice. It is a hackathon project made public as an example of engineering, not a tool to decide what to do with real money.

## The AI layer

A language model proposes worlds to test or settings to try, and writes sentences. It computes no figure: the engine computes, ranks and checks, and code verifies that every figure of a text of the model comes from the engine. That check covers the figures, not the reasoning of the words around them. A sentence written by the model is an explanation of what the engine computed, and nothing more.

## No warranty

The project's own code is provided under the MIT licence, as it is and without warranty of any kind: see [LICENSE](LICENSE). The credits are in [NOTICE](NOTICE).
