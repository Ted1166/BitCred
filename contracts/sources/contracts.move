#[allow(unused_const, unused_variable)]
module bitcred::score_registry {

    use sui::table::{Self, Table};
    use sui::clock::{Self, Clock};

    const MIN_SCORE: u16 = 650;
    const MAX_SCORE: u16 = 850;
    const UPDATE_COOLDOWN_MS: u64 = 2592000000;
    const RATIO_TIER_1: u32 = 11000;
    const RATIO_TIER_2: u32 = 11500;
    const RATIO_TIER_3: u32 = 12000;
    const RATIO_TIER_4: u32 = 13000;
    const RATIO_DEFAULT: u32 = 15000;
    const EInvalidScore: u64 = 0;
    const EAlreadyRegistered: u64 = 1;
    const ENotRegistered: u64 = 2;
    const ECooldownActive: u64 = 3;
    const ENotAuthorized: u64 = 4;

    public struct ScoreRegistry has key {
        id: UID,
        scores: Table<vector<u8>, u16>,
        last_updated: Table<vector<u8>, u64>,
        score_owners: Table<vector<u8>, address>,
        admin: address,
        approved_scorers: Table<address, bool>,
    }

    public struct AdminCap has key, store { id: UID }

    public struct ScoreRegistered has copy, drop {
        btc_address_hash: vector<u8>,
        owner: address,
        score: u16,
        tier: u8,
        collateral_ratio: u32,
        timestamp: u64,
    }

    public struct ScoreUpdated has copy, drop {
        btc_address_hash: vector<u8>,
        old_score: u16,
        new_score: u16,
        timestamp: u64,
    }

    fun init(ctx: &mut TxContext) {
        let admin = ctx.sender();
        let mut registry = ScoreRegistry {
            id: object::new(ctx),
            scores: table::new(ctx),
            last_updated: table::new(ctx),
            score_owners: table::new(ctx),
            admin,
            approved_scorers: table::new(ctx),
        };
        table::add(&mut registry.approved_scorers, admin, true);
        transfer::share_object(registry);
        transfer::transfer(AdminCap { id: object::new(ctx) }, admin);
    }

    public fun register_score(
        registry: &mut ScoreRegistry,
        btc_address_hash: vector<u8>,
        score: u16,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        assert!(score >= MIN_SCORE && score <= MAX_SCORE, EInvalidScore);
        assert!(!table::contains(&registry.scores, btc_address_hash), EAlreadyRegistered);
        let caller = ctx.sender();
        let timestamp = clock::timestamp_ms(clock);
        let tier = score_to_tier(score);
        let ratio = tier_to_ratio(tier);
        table::add(&mut registry.scores, btc_address_hash, score);
        table::add(&mut registry.score_owners, btc_address_hash, caller);
        table::add(&mut registry.last_updated, btc_address_hash, timestamp);
        sui::event::emit(ScoreRegistered {
            btc_address_hash,
            owner: caller,
            score,
            tier,
            collateral_ratio: ratio,
            timestamp,
        });
    }

    public fun update_score(
        registry: &mut ScoreRegistry,
        btc_address_hash: vector<u8>,
        new_score: u16,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        assert!(new_score >= MIN_SCORE && new_score <= MAX_SCORE, EInvalidScore);
        assert!(table::contains(&registry.scores, btc_address_hash), ENotRegistered);
        let caller = ctx.sender();
        let owner = *table::borrow(&registry.score_owners, btc_address_hash);
        let is_scorer = table::contains(&registry.approved_scorers, caller)
            && *table::borrow(&registry.approved_scorers, caller);
        assert!(caller == owner || is_scorer, ENotAuthorized);
        let now = clock::timestamp_ms(clock);
        let last = *table::borrow(&registry.last_updated, btc_address_hash);
        assert!(now - last >= UPDATE_COOLDOWN_MS, ECooldownActive);
        let old_score = *table::borrow(&registry.scores, btc_address_hash);
        *table::borrow_mut(&mut registry.scores, btc_address_hash) = new_score;
        *table::borrow_mut(&mut registry.last_updated, btc_address_hash) = now;
        sui::event::emit(ScoreUpdated {
            btc_address_hash,
            old_score,
            new_score,
            timestamp: now,
        });
    }

    public fun approve_scorer(
        registry: &mut ScoreRegistry,
        _cap: &AdminCap,
        scorer: address,
    ) {
        if (table::contains(&registry.approved_scorers, scorer)) {
            *table::borrow_mut(&mut registry.approved_scorers, scorer) = true;
        } else {
            table::add(&mut registry.approved_scorers, scorer, true);
        }
    }

    public fun revoke_scorer(
        registry: &mut ScoreRegistry,
        _cap: &AdminCap,
        scorer: address,
    ) {
        if (table::contains(&registry.approved_scorers, scorer)) {
            *table::borrow_mut(&mut registry.approved_scorers, scorer) = false;
        }
    }

    public fun get_score(registry: &ScoreRegistry, btc_address_hash: vector<u8>): u16 {
        if (table::contains(&registry.scores, btc_address_hash)) {
            *table::borrow(&registry.scores, btc_address_hash)
        } else { 0 }
    }

    public fun get_collateral_ratio(registry: &ScoreRegistry, btc_address_hash: vector<u8>): u32 {
        if (!table::contains(&registry.scores, btc_address_hash)) { return RATIO_DEFAULT };
        let score = *table::borrow(&registry.scores, btc_address_hash);
        tier_to_ratio(score_to_tier(score))
    }

    public fun get_score_tier(registry: &ScoreRegistry, btc_address_hash: vector<u8>): u8 {
        if (!table::contains(&registry.scores, btc_address_hash)) { return 0 };
        score_to_tier(*table::borrow(&registry.scores, btc_address_hash))
    }

    public fun get_last_updated(registry: &ScoreRegistry, btc_address_hash: vector<u8>): u64 {
        if (table::contains(&registry.last_updated, btc_address_hash)) {
            *table::borrow(&registry.last_updated, btc_address_hash)
        } else { 0 }
    }

    public fun get_owner(registry: &ScoreRegistry, btc_address_hash: vector<u8>): address {
        *table::borrow(&registry.score_owners, btc_address_hash)
    }

    public fun is_approved_scorer(registry: &ScoreRegistry, scorer: address): bool {
        table::contains(&registry.approved_scorers, scorer)
            && *table::borrow(&registry.approved_scorers, scorer)
    }

    fun score_to_tier(score: u16): u8 {
        if (score >= 800) { 1 }
        else if (score >= 750) { 2 }
        else if (score >= 700) { 3 }
        else { 4 }
    }

    fun tier_to_ratio(tier: u8): u32 {
        if (tier == 1) { RATIO_TIER_1 }
        else if (tier == 2) { RATIO_TIER_2 }
        else if (tier == 3) { RATIO_TIER_3 }
        else { RATIO_TIER_4 }
    }
}