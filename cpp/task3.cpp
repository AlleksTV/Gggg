#include <iostream>
#include <cstdlib>
#include <ctime>
using namespace std;

void sortBetweenNegatives(int a[], int n) {
    int left = -1, right = -1;
    for (int i = 0; i < n; i++)
        if (a[i] < 0) {
            if (left == -1) left = i;
            right = i;
        }
    cout << "Left: " << left << ", right: " << right << endl;
    for (int i = left + 1; i < right; i++)
        for (int j = left + 1; j < right - 1; j++)
            if (a[j] > a[j + 1]) swap(a[j], a[j + 1]);
}

void print(int a[], int n) {
    for (int i = 0; i < n; i++) cout << a[i] << " ";
    cout << endl;
}

int main() {
    srand(time(0));
    const int n = 10;
    int a[n];
    for (int i = 0; i < n; i++) a[i] = rand() % 41 - 20;
    print(a, n);
    sortBetweenNegatives(a, n);
    print(a, n);
}
