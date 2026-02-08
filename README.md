# ₿ BitCred

**Privacy-Preserving Bitcoin Collateral Scoring for Undercollateralized DeFi**

BitCred analyzes Bitcoin on-chain behavior to generate dynamic collateral ratios, enabling undercollateralized lending without exposing wallet history. Built on Starknet with zero-knowledge proofs.

[![Demo Video](https://img.shields.io/badge/Demo-Watch%20Now-blue)](#)
[![Live Demo](https://img.shields.io/badge/Demo-Try%20It-green)](#)

---

## 🎯 The Problem

**Bitcoin holders are capital inefficient in DeFi:**
- Lock $150 BTC to borrow $100 (150% collateralization)
- Lose exposure to BTC price action
- Privacy concerns: entire wallet history visible on-chain

**Diamond hands holders deserve better rates**, but proving credibility means exposing:
- Total BTC holdings
- Transaction patterns
- Wallet associations

**BitCred solves this** with privacy-preserving credibility scores.

---

## 💡 Our Solution

```
BTC Wallet History → ZK Analysis → Credibility Score → Dynamic Collateral Ratio
     ↓                    ↓              ↓                    ↓
  Hodl Duration      AI Scoring     650-850 Range      110%-130% ratios
  Tx Patterns        STARKs         Verified Proof     Better Rates
  Balance Stability  Private        On-Chain Hash      Keep Privacy
```

### How It Works

1. **Connect Wallet** - Link Bitcoin wallet via Xverse
2. **ZK Proof Generation** - On-chain history analyzed privately
3. **AI Scoring** - Algorithm evaluates:
   - Hodl duration (40%) - Long-term holders score higher
   - Transaction frequency (30%) - Consistent activity preferred
   - Balance stability (30%) - Less volatility = better score
4. **Credibility Score** - 650-850 range, only hash published
5. **Borrow** - Unlock 110%-130% collateral ratios based on score

**Example:**
- Traditional DeFi: Lock 1.5 BTC, borrow 1 BTC worth of USDC
- BitCred (score 800): Lock 1.15 BTC, borrow 1 BTC worth of USDC
- **Savings: 0.35 BTC stays liquid**

---

## 🏗️ Architecture

```
┌─────────────────────┐
│   Frontend          │
│   (Next.js)         │
│   - Xverse SDK      │
│   - Starknet.js     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Starknet Contracts │
│  (Cairo)            │
│  - Score Registry   │
│  - Lending Logic    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  ZK Proof System    │
│  (STARKs)           │
│  - BTC Tx Parser    │
│  - Privacy Layer    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  AI Scoring Engine  │
│  (Python)           │
│  - Behavior Model   │
│  - Risk Assessment  │
└─────────────────────┘
```

### Tech Stack

**Frontend:**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Xverse Wallet SDK
- Starknet.js / starknet-react

**Smart Contracts:**
- Cairo 2.6+
- Starknet Sepolia Testnet
- OpenZeppelin Cairo contracts

**Backend:**
- Python 3.11+
- Bitcoin RPC (via Xverse API)
- STARK proof generation
- AI/ML scoring model

**Infrastructure:**
- Vercel (Frontend)
- Starknet Sepolia
- Bitcoin Mainnet/Testnet

---

## 🚀 Getting Started

### Prerequisites

```bash
# Required
- Node.js 18+
- Xverse Wallet (Bitcoin + Starknet)
- Starknet Sepolia ETH (from faucet)
- Scarb 2.6+ (Cairo package manager)
- Python 3.11+
```

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/bitcred.git
cd bitcred
```

2. **Frontend Setup**
```bash
cd frontend
npm install
```

3. **Environment Configuration**
```bash
# Create .env.local
cat > .env.local << EOF
NEXT_PUBLIC_STARKNET_CHAIN_ID=SN_SEPOLIA
NEXT_PUBLIC_SCORE_REGISTRY_ADDRESS=0x...
NEXT_PUBLIC_LENDING_CONTRACT_ADDRESS=0x...
XVERSE_API_KEY=your_api_key_here
EOF
```

4. **Run Frontend**
```bash
npm run dev
# Open http://localhost:3000
```

### Smart Contracts Setup

1. **Navigate to contracts**
```bash
cd contracts
```

2. **Build contracts**
```bash
scarb build
```

3. **Deploy to Starknet Sepolia**
```bash
starkli deploy target/dev/bitcred_ScoreRegistry.contract_class.json \
  --network sepolia \
  --account ~/.starkli-wallets/deployer/account.json
```

### Backend Setup

1. **Navigate to backend**
```bash
cd backend
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run scoring service**
```bash
python src/scorer.py
```

---

## 📊 Credibility Scoring Algorithm

### Score Components (300 total points)

```python
# 1. Hodl Duration Score (120 points max)
hodl_score = min(120, days_since_first_tx / 30 * 10)
# 1 year = 120 points, 6 months = 60 points

# 2. Transaction Consistency (90 points max)
tx_frequency = total_txs / months_active
consistency_score = min(90, tx_frequency * 15)
# 6 txs/month = 90 points, 3 txs/month = 45 points

# 3. Balance Stability (90 points max)
volatility = std_dev(monthly_balances) / mean(monthly_balances)
stability_score = max(0, 90 - (volatility * 100))
# Low volatility = 90 points, high volatility = 0 points

# Final Credibility Score
raw_score = hodl_score + consistency_score + stability_score
final_score = 650 + (raw_score * 0.67)  # Scale to 650-850
```

### Collateral Ratio Mapping

| Score Range | Credibility Tier | Collateral Ratio | Example           |
|-------------|------------------|------------------|-------------------|
| 800-850     | Diamond Hands    | 110%             | Lock 1.1 BTC → Borrow 1 BTC |
| 750-799     | Strong Holder    | 115%             | Lock 1.15 BTC → Borrow 1 BTC |
| 700-749     | Moderate Holder  | 120%             | Lock 1.2 BTC → Borrow 1 BTC |
| 650-699     | New Holder       | 130%             | Lock 1.3 BTC → Borrow 1 BTC |

---

## 🔐 Privacy & Security

### How Privacy is Preserved

✅ **ZK Proofs** - Verify BTC history without revealing details  
✅ **Hash-Only Storage** - Only score hash stored on-chain  
✅ **No Wallet Linking** - BTC and Starknet addresses not associated  
✅ **Selective Disclosure** - Users choose what to prove  
✅ **Non-Custodial** - No BTC leaves user's wallet during scoring  

### Security Model

- **Bitcoin L1 Security**: Inherit Bitcoin's PoW security
- **Starknet L2 Security**: STARK proofs verify all computations
- **No Oracle Risk**: Direct Bitcoin chain analysis
- **Decentralized Scoring**: Open-source algorithm, verifiable on-chain

---

## 🎬 Demo Flow

1. **Connect Xverse Wallet** - Bitcoin + Starknet addresses
2. **Authorize Analysis** - Sign message to prove wallet ownership
3. **Generate ZK Proof** - Bitcoin history analyzed (2-3 mins)
4. **View Credibility Score** - 650-850 with tier classification
5. **Access Lending** - Borrow with improved collateral ratio

**Processing Time:** 2-5 minutes  
**Privacy:** Only score hash published on-chain  
**Cost:** ~0.001 ETH gas on Starknet Sepolia

---

## 🌍 Real-World Impact

### Target Users

**Long-Term Bitcoin Holders:**
- 💎 Early adopters with multi-year hodl history
- 🏦 Custodians needing capital efficiency
- 📊 Institutions with proven track records

**Benefits:**
- Unlock 20-40% more capital efficiency
- Maintain BTC exposure while borrowing
- Privacy-preserved wallet history
- Portable credibility across DeFi protocols

### Market Opportunity

- **$500B+ BTC market cap**
- **<1% utilized in DeFi** (mostly over-collateralized)
- **Potential unlock: $5B+ in undercollateralized lending**

---

## 🧪 Testing

### Local Testing

```bash
# Test Cairo contracts
cd contracts
scarb test

# Test scoring algorithm
cd backend
pytest tests/test_scorer.py

# Expected output:
# ✓ Score calculation: 785 (Strong Holder)
# ✓ Collateral ratio: 115%
# ✓ ZK proof generation: Valid
```

### Integration Testing

```bash
# Run full integration suite
npm run test:integration

# E2E tests
npm run test:e2e
```

---

## 📝 Smart Contracts

### Deployed Contracts (Starknet Sepolia)

**Score Registry:**
```
Coming soon...
```

**Lending Pool:**
```
Coming soon...
```

### Verify on Explorer

[View on Voyager](#)

---

## 🗺️ Roadmap

### Phase 1: Hackathon (Feb 2025)
- [x] Core credibility scoring algorithm
- [x] Basic Cairo contracts
- [ ] Xverse integration
- [ ] ZK proof generation
- [ ] Demo deployment

### Phase 2: Testnet Launch (Mar 2025)
- [ ] Audit smart contracts
- [ ] Advanced scoring (multi-wallet aggregation)
- [ ] Liquidity pools integration
- [ ] Beta user testing

### Phase 3: Mainnet (Q2 2025)
- [ ] Mainnet deployment
- [ ] Insurance fund
- [ ] Multi-chain support (Bitcoin L2s)
- [ ] Governance token

---

## 🤝 Contributing

### Development Setup

1. Fork the repo
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

### Contribution Guidelines

- Follow Cairo style guide for smart contracts
- Add tests for all new features
- Update documentation
- Sign commits with GPG key

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 👥 Team

- **Ted Adams** - Smart Contracts & Backend - [@yourtwitter](https://twitter.com/yourtwitter)
- **Peter Kagwe** - Cairo Development - [@peter](https://twitter.com/peter)
- **[Team Member 3]** - Frontend & Integration - [@handle](https://twitter.com/handle)

---

## 🙏 Acknowledgments

- **Starknet Foundation** - For hackathon support and infrastructure
- **Xverse** - For Bitcoin wallet SDK and API access
- **StarkWare** - For STARK proof technology
- **Bitcoin Community** - For building the foundation

---

## 📞 Contact

- **Website**: [bitcred.xyz](#)
- **Twitter**: [@BitCredProtocol](#)
- **Email**: team@bitcred.xyz
- **Telegram**: [BitCred Community](#)

---

<div align="center">

**Built with ₿ for Bitcoin Holders**

*Unlock Capital. Keep Privacy. Prove Credibility.*

</div>