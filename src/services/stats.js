"use strict";

const { Exposition, Visit } = require("../models");

async function totalExpos() {
  return Exposition.count();
}

async function userDoneCount(user) {
  return Visit.count({ where: { user_id: user.id } });
}

async function progress(user) {
  const total = await totalExpos();
  const done = await userDoneCount(user);
  const pct = total ? Math.round((done / total) * 100) : 0;
  return { total, done, remaining: Math.max(total - done, 0), pct };
}

async function funStats(user) {
  const daysLeft = user.days_until_26;
  const p = await progress(user);
  const remaining = p.remaining;

  const stats = {
    days_until_26: daysLeft,
    is_over_26: daysLeft < 0,
    weeks_until_26: Math.max(Math.trunc(daysLeft / 7), 0),
    expos_per_week: null,
    expos_per_month: null,
  };

  const weeks = daysLeft > 0 ? daysLeft / 7 : 0;
  if (weeks > 0 && remaining > 0) {
    stats.expos_per_week = Math.round((remaining / weeks) * 10) / 10;
    stats.expos_per_month = Math.round((remaining / (daysLeft / 30)) * 10) / 10;
  }
  return stats;
}

module.exports = { totalExpos, userDoneCount, progress, funStats };
