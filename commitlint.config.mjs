export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'subject-case': [0],
    'header-max-length': [2, 'always', 100],
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'style',
        'refactor',
        'perf',
        'test',
        'build',
        'ci',
        'chore',
        'revert',
      ],
    ],
  },
}
