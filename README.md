# Portfolio-Tracker: Multi-Client Angel One Portfolio Sync

> Python service that logs in to multiple Angel One accounts, pulls holdings, computes stock-level and overall P&L and upserts a single snapshot document per client into primary **and** backup MongoDB databases.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white) ![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat-square&logo=mongodb&logoColor=white) ![Angel One SmartAPI](https://img.shields.io/badge/Angel%20One%20SmartAPI-E4572E?style=flat-square)

**Related:** Live dashboard (demo data): [portfolio-tracker-frontend-2.vercel.app](https://portfolio-tracker-frontend-2.vercel.app)

## Features

- Multi-client login with TOTP
- One document per client: idempotent upserts for existing and new holdings
- Writes to a primary and a backup database
- Structured logging tagged by client code, with noisy third-party logs suppressed
- `v1` and `v2` implementations

## Usage

```bash
git clone https://github.com/optimus-node-js/Portfolio-Tracker.git
cd Portfolio-Tracker
```

```bash
pip install smartapi-python pyotp pymongo logzero
python portfolio_tracker_v2.py
```

Provide your own API keys, client codes and MongoDB URIs via environment variables.

**This is the data layer of a full stack:** [Portfolio-Tracker-Backend](https://github.com/optimus-node-js/Portfolio-Tracker-Backend) (API) [Portfolio-Tracker-Frontend](https://github.com/optimus-node-js/Portfolio-Tracker-Frontend) (dashboard).

---

## Author

**Rahul Vishwakarma**, Senior Full Stack Developer based in Ahmedabad, India

[![Portfolio](https://img.shields.io/badge/Portfolio-rahul--vishwakarma--portfolio.vercel.app-0A66C2?style=flat-square&logo=vercel&logoColor=white)](https://rahul-vishwakarma-portfolio.vercel.app/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Rahul%20Vishwakarma-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/rahul-vishwakarma-101346192)
[![Email](https://img.shields.io/badge/Email-karmarahul67%40gmail.com-D14836?style=flat-square&logo=gmail&logoColor=white)](mailto:karmarahul67@gmail.com)
[![GitHub](https://img.shields.io/badge/GitHub-optimus--node--js-181717?style=flat-square&logo=github)](https://github.com/optimus-node-js)

