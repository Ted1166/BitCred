#[allow(unused_const, unused_field, lint(self_transfer))]
module bitcred::lending_pool {

    use sui::table::{Self, Table};
    use sui::clock::{Self, Clock};
    use sui::coin::{Self, Coin};
    use sui::balance::{Self, Balance};
    use bitcred::score_registry::{Self, ScoreRegistry};

    const BTC_PRICE_USDC: u64 = 90_000_000_000;
    const INTEREST_RATE_BPS: u64 = 500;
    const SECONDS_PER_YEAR: u64 = 31_536_000_000;
    const LIQUIDATION_THRESHOLD: u64 = 10_000;
    const LIQUIDATION_BONUS_BPS: u64 = 500;
    const MIN_SCORE: u16 = 650;

    const EZeroAmount: u64 = 0;
    const ENoScore: u64 = 1;
    const EExceedsBorrow: u64 = 2;
    const EInsufficientLiquidity: u64 = 3;
    const ENoDebt: u64 = 4;
    const EDebtNotCleared: u64 = 5;
    const EHealthy: u64 = 6;
    const ENotAdmin: u64 = 7;
    const EExceedsCollateral: u64 = 8;

    public struct WBTC has drop {}
    public struct USDC has drop {}

    public struct LendingPool has key {
        id: UID,
        admin: address,
        collateral_reserves: Balance<WBTC>,
        usdc_reserves: Balance<USDC>,
        collateral_deposits: Table<address, u64>,
        borrowed_amounts: Table<address, u64>,
        borrow_timestamps: Table<address, u64>,
        user_btc_hash: Table<address, vector<u8>>,
        cached_ratio: Table<address, u32>,
    }

    public struct CollateralDeposited has copy, drop {
        user: address,
        amount: u64,
        btc_address_hash: vector<u8>,
    }

    public struct Borrowed has copy, drop {
        user: address,
        amount: u64,
        collateral_ratio: u32,
    }

    public struct Repaid has copy, drop {
        user: address,
        amount: u64,
    }

    public struct CollateralWithdrawn has copy, drop {
        user: address,
        amount: u64,
    }

    public struct Liquidated has copy, drop {
        user: address,
        liquidator: address,
        debt_repaid: u64,
        collateral_seized: u64,
    }

    fun init(ctx: &mut TxContext) {
        let pool = LendingPool {
            id: object::new(ctx),
            admin: ctx.sender(),
            collateral_reserves: balance::zero(),
            usdc_reserves: balance::zero(),
            collateral_deposits: table::new(ctx),
            borrowed_amounts: table::new(ctx),
            borrow_timestamps: table::new(ctx),
            user_btc_hash: table::new(ctx),
            cached_ratio: table::new(ctx),
        };
        transfer::share_object(pool);
    }

    public fun deposit_collateral(
        pool: &mut LendingPool,
        registry: &ScoreRegistry,
        collateral: Coin<WBTC>,
        btc_address_hash: vector<u8>,
        ctx: &mut TxContext,
    ) {
        let amount = coin::value(&collateral);
        assert!(amount > 0, EZeroAmount);
        let score = score_registry::get_score(registry, btc_address_hash);
        assert!(score >= MIN_SCORE, ENoScore);
        let caller = ctx.sender();
        let ratio = score_registry::get_collateral_ratio(registry, btc_address_hash);
        balance::join(&mut pool.collateral_reserves, coin::into_balance(collateral));
        if (table::contains(&pool.collateral_deposits, caller)) {
            let existing = *table::borrow(&pool.collateral_deposits, caller);
            *table::borrow_mut(&mut pool.collateral_deposits, caller) = existing + amount;
        } else {
            table::add(&mut pool.collateral_deposits, caller, amount);
        };
        if (!table::contains(&pool.user_btc_hash, caller)) {
            table::add(&mut pool.user_btc_hash, caller, btc_address_hash);
        };
        if (table::contains(&pool.cached_ratio, caller)) {
            *table::borrow_mut(&mut pool.cached_ratio, caller) = ratio;
        } else {
            table::add(&mut pool.cached_ratio, caller, ratio);
        };
        sui::event::emit(CollateralDeposited { user: caller, amount, btc_address_hash });
    }

    public fun borrow(
        pool: &mut LendingPool,
        registry: &ScoreRegistry,
        amount: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ): Coin<USDC> {
        assert!(amount > 0, EZeroAmount);
        let caller = ctx.sender();
        let btc_hash = *table::borrow(&pool.user_btc_hash, caller);
        let ratio_bps = score_registry::get_collateral_ratio(registry, btc_hash);
        *table::borrow_mut(&mut pool.cached_ratio, caller) = ratio_bps;
        let collateral = *table::borrow(&pool.collateral_deposits, caller);
        let collateral_usd = (collateral * BTC_PRICE_USDC) / 100_000_000;
        let max_borrow = (collateral_usd * 10_000) / (ratio_bps as u64);
        let current_debt = compute_debt(pool, caller, clock);
        assert!(current_debt + amount <= max_borrow, EExceedsBorrow);
        assert!(amount <= balance::value(&pool.usdc_reserves), EInsufficientLiquidity);
        let now = clock::timestamp_ms(clock);
        if (table::contains(&pool.borrowed_amounts, caller)) {
            let principal = *table::borrow(&pool.borrowed_amounts, caller);
            let accrued = current_debt - principal;
            *table::borrow_mut(&mut pool.borrowed_amounts, caller) = principal + accrued + amount;
            *table::borrow_mut(&mut pool.borrow_timestamps, caller) = now;
        } else {
            table::add(&mut pool.borrowed_amounts, caller, amount);
            table::add(&mut pool.borrow_timestamps, caller, now);
        };
        sui::event::emit(Borrowed { user: caller, amount, collateral_ratio: ratio_bps });
        coin::from_balance(balance::split(&mut pool.usdc_reserves, amount), ctx)
    }

    public fun repay(
        pool: &mut LendingPool,
        payment: Coin<USDC>,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let caller = ctx.sender();
        let total_debt = compute_debt(pool, caller, clock);
        assert!(total_debt > 0, ENoDebt);
        let paid = coin::value(&payment);
        let repay_amount = if (paid > total_debt) { total_debt } else { paid };
        let mut payment_balance = coin::into_balance(payment);
        if (paid > repay_amount) {
            let excess = balance::split(&mut payment_balance, paid - repay_amount);
            transfer::public_transfer(coin::from_balance(excess, ctx), caller);
        };
        balance::join(&mut pool.usdc_reserves, payment_balance);
        let principal = *table::borrow(&pool.borrowed_amounts, caller);
        let new_principal = if (repay_amount >= principal) { 0 } else { principal - repay_amount };
        *table::borrow_mut(&mut pool.borrowed_amounts, caller) = new_principal;
        let now = clock::timestamp_ms(clock);
        *table::borrow_mut(&mut pool.borrow_timestamps, caller) = if (new_principal == 0) { 0 } else { now };
        sui::event::emit(Repaid { user: caller, amount: repay_amount });
    }

    public fun withdraw_collateral(
        pool: &mut LendingPool,
        amount: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ): Coin<WBTC> {
        let caller = ctx.sender();
        assert!(compute_debt(pool, caller, clock) == 0, EDebtNotCleared);
        let deposited = *table::borrow(&pool.collateral_deposits, caller);
        assert!(amount <= deposited, EExceedsCollateral);
        *table::borrow_mut(&mut pool.collateral_deposits, caller) = deposited - amount;
        sui::event::emit(CollateralWithdrawn { user: caller, amount });
        coin::from_balance(balance::split(&mut pool.collateral_reserves, amount), ctx)
    }

    public fun add_liquidity(
        pool: &mut LendingPool,
        liquidity: Coin<USDC>,
        ctx: &mut TxContext,
    ) {
        assert!(ctx.sender() == pool.admin, ENotAdmin);
        balance::join(&mut pool.usdc_reserves, coin::into_balance(liquidity));
    }

    public fun get_collateral(pool: &LendingPool, user: address): u64 {
        if (table::contains(&pool.collateral_deposits, user)) {
            *table::borrow(&pool.collateral_deposits, user)
        } else { 0 }
    }

    public fun get_total_debt(pool: &LendingPool, user: address, clock: &Clock): u64 {
        compute_debt(pool, user, clock)
    }

    public fun get_available_liquidity(pool: &LendingPool): u64 {
        balance::value(&pool.usdc_reserves)
    }

    public fun get_health_factor(pool: &LendingPool, user: address, clock: &Clock): u64 {
        let debt = compute_debt(pool, user, clock);
        if (debt == 0) { return 99_999 };
        let collateral = *table::borrow(&pool.collateral_deposits, user);
        let collateral_usd = (collateral * BTC_PRICE_USDC) / 100_000_000;
        (collateral_usd * 10_000) / debt
    }

    fun compute_debt(pool: &LendingPool, user: address, clock: &Clock): u64 {
        if (!table::contains(&pool.borrowed_amounts, user)) { return 0 };
        let principal = *table::borrow(&pool.borrowed_amounts, user);
        if (principal == 0) { return 0 };
        let ts = *table::borrow(&pool.borrow_timestamps, user);
        if (ts == 0) { return principal };
        let now = clock::timestamp_ms(clock);
        let elapsed = now - ts;
        let interest = (principal * INTEREST_RATE_BPS * elapsed) / (10_000 * SECONDS_PER_YEAR);
        principal + interest
    }
}