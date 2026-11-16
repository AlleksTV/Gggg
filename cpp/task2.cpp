#include <iostream>
using namespace std;

void sortHalves(int a[], int n) {
    int h = n / 2;
    // first half - descending
    for (int i = 1; i < h; i++) {
        int x = a[i], j = i - 1;
        while (j >= 0 && a[j] < x) { a[j + 1] = a[j]; j--; }
        a[j + 1] = x;
    }
    // second half - ascending
    for (int i = h + 1; i < n; i++) {
        int x = a[i], j = i - 1;
        while (j >= h && a[j] > x) { a[j + 1] = a[j]; j--; }
        a[j + 1] = x;
    }
}

int main() {
    int a[10] = {5, 2, 9, 1, 7, 3, 8, 6, 4, 0};
    sortHalves(a, 10);
    for (int i = 0; i < 10; i++) cout << a[i] << " ";
    cout << endl;
}
